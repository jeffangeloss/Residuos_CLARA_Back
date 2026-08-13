"""Pruebas de cantidad, unidad y modos de medición."""

import pytest
from pydantic import ValidationError

from tests.test_persistencia import _entrada, _persistir


def _clasificar(**cambios):
    from core.classifier import clasificar_residuo

    return clasificar_residuo(_entrada(**cambios))


@pytest.fixture()
def sin_exigir_pesaje(monkeypatch):
    """Levanta la política de pesaje obligatorio.

    El modelo admite litros aunque la captura no los acepte: el formato oficial
    los contempla y los 277 registros históricos en litros tienen que poder
    importarse. Esta marca aísla esa capacidad de la política vigente.
    """
    import core.models

    monkeypatch.setattr(core.models, "EXIGIR_PESAJE_EN_KG", False)


# --------------------------------------------------------------------------
# Modo pesaje
# --------------------------------------------------------------------------

def test_el_pesaje_produce_la_cantidad_en_kilogramos():
    resultado = _clasificar(peso_bruto_g=2600.0, tara_g=200.0)

    assert resultado.peso_neto_g == 2400.0
    assert resultado.cantidad == 2.4
    assert resultado.unidad == "Kg"
    assert resultado.modo_medicion == "pesaje"


def test_el_pesaje_conserva_su_evidencia():
    resultado = _clasificar(peso_bruto_g=1500.0, tara_g=150.0)

    assert resultado.peso_bruto_g == 1500.0
    assert resultado.tara_g == 150.0
    assert resultado.peso_neto_g == 1350.0


def test_un_pesaje_no_puede_declararse_en_litros():
    with pytest.raises(ValidationError):
        _entrada(peso_bruto_g=1000.0, unidad="L")


# --------------------------------------------------------------------------
# Modo declaración directa
# --------------------------------------------------------------------------

def test_la_captura_exige_pesaje_en_kilogramos():
    """Decisión del 2026-08-13: toda declaración nueva se pesa en balanza."""
    with pytest.raises(ValidationError, match="balanza"):
        _entrada(peso_bruto_g=None, cantidad=5.0, unidad="L")

    with pytest.raises(ValidationError, match="balanza"):
        _entrada(peso_bruto_g=None, cantidad=2.0, unidad="Kg")


def test_se_puede_declarar_volumen_sin_balanza(sin_exigir_pesaje):
    """277 de los 856 registros históricos están en litros.

    La capacidad se conserva aunque la política vigente no la permita en
    captura: sin ella no se podrían importar esos registros.
    """
    resultado = _clasificar(peso_bruto_g=None, tara_g=0.0, cantidad=5.0, unidad="L")

    assert resultado.cantidad == 5.0
    assert resultado.unidad == "L"
    assert resultado.modo_medicion == "declarada"
    assert resultado.peso_neto_g is None


def test_una_cantidad_declarada_en_litros_persiste_tal_cual(db, sin_exigir_pesaje):
    declaracion = _persistir(db, peso_bruto_g=None, tara_g=0.0, cantidad=3.7, unidad="L")

    assert declaracion.cantidad == 3.7
    assert declaracion.unidad == "L"
    assert declaracion.peso_neto_g is None


def test_el_kardex_de_un_residuo_por_volumen_no_inventa_masa(db, sin_exigir_pesaje):
    """Sin balanza no hay gramos que registrar; mejor nulo que cero."""
    declaracion = _persistir(db, peso_bruto_g=None, tara_g=0.0, cantidad=3.7, unidad="L")

    assert declaracion.movimientos[0].cantidad_g is None


# --------------------------------------------------------------------------
# Exclusividad de los modos
# --------------------------------------------------------------------------

def test_hay_que_indicar_alguna_forma_de_medir(sin_exigir_pesaje):
    with pytest.raises(ValidationError):
        _entrada(peso_bruto_g=None, cantidad=None)


def test_no_se_pueden_indicar_las_dos_a_la_vez():
    """La cantidad sale del pesaje: darlas juntas permite que se contradigan."""
    with pytest.raises(ValidationError):
        _entrada(peso_bruto_g=1000.0, cantidad=0.9)


def test_la_cantidad_debe_ser_positiva(sin_exigir_pesaje):
    with pytest.raises(ValidationError):
        _entrada(peso_bruto_g=None, cantidad=0.0, unidad="L")


# --------------------------------------------------------------------------
# Advertencias de unidad
# --------------------------------------------------------------------------

def test_una_masa_declarada_sin_balanza_se_advierte(sin_exigir_pesaje):
    """El curador del Excel histórico anotó este caso 195 veces."""
    resultado = _clasificar(peso_bruto_g=None, tara_g=0.0, cantidad=2.0, unidad="Kg")

    assert any("balanza" in obs.lower() for obs in resultado.observaciones)


def test_una_masa_pesada_no_lleva_esa_advertencia():
    resultado = _clasificar(peso_bruto_g=2000.0, tara_g=100.0)

    assert not any("balanza" in obs.lower() for obs in resultado.observaciones)


def test_un_solido_declarado_en_litros_se_advierte(sin_exigir_pesaje):
    resultado = _clasificar(
        peso_bruto_g=None, tara_g=0.0, cantidad=5.0, unidad="L",
        estado_fisico="Sólido", es_punzocortante=True, insumos=[],
    )

    assert any("sólido declarado en litros" in obs.lower() for obs in resultado.observaciones)


def test_un_liquido_en_litros_no_lleva_advertencia(sin_exigir_pesaje):
    resultado = _clasificar(peso_bruto_g=None, tara_g=0.0, cantidad=5.0, unidad="L")

    assert not any("litros" in obs.lower() for obs in resultado.observaciones)
    assert not any("balanza" in obs.lower() for obs in resultado.observaciones)


# --------------------------------------------------------------------------
# Totales y exportación
# --------------------------------------------------------------------------

def test_los_totales_no_suman_kilogramos_con_litros(db, sin_exigir_pesaje):
    """Sumar masa y volumen no produce ninguna magnitud."""
    import openpyxl
    from core.artifacts import workbook_declaracion
    from core.repositorio import declaraciones_del_periodo

    _persistir(db, fecha="2026-08-12", peso_bruto_g=2000.0, tara_g=0.0)
    _persistir(db, fecha="2026-08-12", peso_bruto_g=None, tara_g=0.0,
               cantidad=5.0, unidad="L", insumos=["acetona"])

    libro = openpyxl.load_workbook(
        workbook_declaracion(declaraciones_del_periodo(db, 8, 2026), 8, 2026))
    totales = {fila[0]: fila[1] for fila in libro["Totales"].iter_rows(values_only=True)}

    assert totales["Cantidad total declarada en kg"] == 2.0
    assert totales["Cantidad total declarada en L"] == 5.0


def test_la_etiqueta_imprime_la_unidad_declarada(db, sin_exigir_pesaje):
    from core.artifacts import etiqueta_pdf
    from core.repositorio import consulta_declaraciones

    _persistir(db, peso_bruto_g=None, tara_g=0.0, cantidad=3.7, unidad="L")
    registro = consulta_declaraciones(db).first()

    assert etiqueta_pdf(registro).getvalue()[:4] == b"%PDF"
    assert registro.unidad == "L"
