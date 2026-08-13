"""Pruebas del nivel de confianza y de las observaciones del clasificador.

No requieren base de datos: ejercitan el motor determinista directamente.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.classifier import clasificar_residuo  # noqa: E402
from core.models import EntradaResiduoRequest  # noqa: E402


def _entrada(**cambios):
    datos = {
        "dependencia": "Ingeniería Industrial",
        "laboratorio": "Química General",
        "actividad": "Ensayo",
        "responsable": "Lic. Álvarez",
        "fecha": "2026-08-13",
        "descripcion": "Residuo de laboratorio",
        "insumos": ["ácido sulfúrico 98%"],
        "peso_bruto_g": 1000.0,
        "tara_g": 100.0,
    }
    datos.update(cambios)
    return EntradaResiduoRequest(**datos)


def test_indicador_explicito_da_confianza_alta():
    """El usuario declaró la naturaleza del residuo; no hay que adivinarla."""
    resultado = clasificar_residuo(_entrada(es_punzocortante=True, insumos=[]))

    assert resultado.categoria_id == "punzocortantes"
    assert resultado.confianza == "Alto"


def test_categoria_deducida_de_insumos_da_confianza_media():
    """La RF-04 pide tres niveles; antes el motor solo emitía Alto y Bajo."""
    resultado = clasificar_residuo(_entrada(insumos=["ácido sulfúrico 98%"]))

    assert resultado.categoria_id == "acidos-corrosivos"
    assert resultado.confianza == "Medio"


def test_composicion_desconocida_da_confianza_baja():
    resultado = clasificar_residuo(_entrada(desconocido=True, insumos=[]))

    assert resultado.categoria_id == "no-identificados"
    assert resultado.confianza == "Bajo"
    assert resultado.escalar_csbqr is True


def test_insumos_no_reconocidos_dan_confianza_baja():
    resultado = clasificar_residuo(_entrada(insumos=["sustancia sin coincidencia conocida"]))

    assert resultado.categoria_id == "no-identificados"
    assert resultado.confianza == "Bajo"


def test_categoria_deducida_avisa_que_hay_que_verificarla():
    resultado = clasificar_residuo(_entrada(insumos=["acetona"]))

    assert any("verifique" in obs.lower() for obs in resultado.observaciones)


def test_categoria_declarada_no_lleva_ese_aviso():
    resultado = clasificar_residuo(_entrada(es_biologico=True, insumos=[]))

    assert not any("verifique" in obs.lower() for obs in resultado.observaciones)


def test_tara_mayor_que_el_bruto_se_advierte_sin_bloquear():
    """La RF-02 define el neto como máximo entre cero y la diferencia.

    El caso se acepta, pero casi siempre significa que los campos se llenaron
    al revés, así que la declaración sale con la advertencia visible.
    """
    resultado = clasificar_residuo(_entrada(peso_bruto_g=100.0, tara_g=500.0))

    assert resultado.peso_neto_g == 0.0
    assert any("tara supera" in obs.lower() for obs in resultado.observaciones)


def test_observaciones_de_manejo_siempre_presentes():
    resultado = clasificar_residuo(_entrada())

    assert "Llenar como máximo al 75%" in resultado.observaciones
    assert "No verter al desagüe" in resultado.observaciones


def test_nombre_normalizado_se_recorta_a_la_columna():
    resultado = clasificar_residuo(_entrada(insumos=[f"reactivo {i}" for i in range(60)]))

    assert len(resultado.nombre_normalizado) <= 300
