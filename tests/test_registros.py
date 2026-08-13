"""Pruebas de la estructura maestro-detalle y de los códigos del sistema."""

from datetime import date

import pytest

from tests.test_persistencia import _entrada, _persistir


def _abrir_registro(db, **cambios):
    from core.repositorio import crear_registro

    datos = {
        "dependencia": "Ingeniería Industrial",
        "laboratorio": "Química General",
        "responsable_encargado": "Lic. Álvarez",
        "fecha": date(2026, 8, 13),
    }
    datos.update(cambios)
    return crear_registro(db, **datos)


# --------------------------------------------------------------------------
# Estructura maestro-detalle
# --------------------------------------------------------------------------

def test_un_registro_agrupa_varios_residuos(db):
    """El caso real: una visita con muchos envases y una sola cabecera."""
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    registro = _abrir_registro(db)
    for insumo in ["ácido sulfúrico 98%", "acetona", "hidróxido de sodio"]:
        entrada = _entrada(insumos=[insumo], fecha="2026-08-13")
        crear_declaracion(db, entrada, clasificar_residuo(entrada), registro=registro)

    db.refresh(registro)
    assert len(registro.declaraciones) == 3
    # La cabecera se guarda una sola vez, no repetida en cada residuo.
    assert registro.responsable_encargado == "Lic. Álvarez"
    assert {d.registro_id for d in registro.declaraciones} == {registro.id}


def test_el_laboratorio_vive_en_la_cabecera(db):
    declaracion = _persistir(db)

    assert declaracion.registro is not None
    assert declaracion.laboratorio is declaracion.registro.laboratorio
    assert declaracion.laboratorio.nombre == "Química General"


def test_los_dos_responsables_son_independientes(db):
    """El encargado del laboratorio no es quien generó cada residuo."""
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    registro = _abrir_registro(db, responsable_encargado="Dra. Mendoza")
    entrada = _entrada(responsable="Ing. Ramírez", fecha="2026-08-13")
    declaracion = crear_declaracion(db, entrada, clasificar_residuo(entrada), registro=registro)

    assert declaracion.registro.responsable_encargado == "Dra. Mendoza"
    assert declaracion.responsable == "Ing. Ramírez"


def test_borrar_el_registro_arrastra_sus_residuos(db):
    from core.db_models import DeclaracionResiduoDB
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    registro = _abrir_registro(db)
    for insumo in ["acetona", "etanol"]:
        entrada = _entrada(insumos=[insumo], fecha="2026-08-13")
        crear_declaracion(db, entrada, clasificar_residuo(entrada), registro=registro)

    db.delete(registro)
    db.commit()

    assert db.query(DeclaracionResiduoDB).count() == 0


# --------------------------------------------------------------------------
# Resolución del registro desde una captura suelta
# --------------------------------------------------------------------------

def test_capturas_del_mismo_dia_y_laboratorio_comparten_registro(db):
    """El endpoint heredado no debe abrir una visita por cada envase."""
    from core.db_models import RegistroDB

    primera = _persistir(db, fecha="2026-08-13", insumos=["acetona"])
    segunda = _persistir(db, fecha="2026-08-13", insumos=["etanol"])

    assert primera.registro_id == segunda.registro_id
    assert db.query(RegistroDB).count() == 1


def test_capturas_de_dias_distintos_abren_registros_distintos(db):
    from core.db_models import RegistroDB

    _persistir(db, fecha="2026-08-13")
    _persistir(db, fecha="2026-08-14")

    assert db.query(RegistroDB).count() == 2


def test_capturas_de_laboratorios_distintos_abren_registros_distintos(db):
    from core.db_models import RegistroDB

    _persistir(db, fecha="2026-08-13", laboratorio="Química General")
    _persistir(db, fecha="2026-08-13", laboratorio="Química Analítica")

    assert db.query(RegistroDB).count() == 2


# --------------------------------------------------------------------------
# Códigos
# --------------------------------------------------------------------------

@pytest.mark.parametrize("nombre,esperado", [
    ("Silvia Ponce", "SPON"),
    ("Javier Quino", "JQUI"),
    ("Juan Carlos Yacono Llanos", "JCYL"),
    ("Álvarez", "ALVA"),
    ("", "XXXX"),
])
def test_sufijo_de_persona(nombre, esperado):
    from core.codigos import sufijo_persona

    assert sufijo_persona(nombre) == esperado


def test_formato_del_codigo_de_registro(db):
    registro = _abrir_registro(db)

    assert registro.codigo == "13082026000000-ALVA"


def test_los_codigos_de_registro_no_colisionan_en_la_misma_fecha(db):
    from core.db_models import RegistroDB

    _abrir_registro(db, laboratorio="Química General")
    _abrir_registro(db, laboratorio="Química Analítica")
    _abrir_registro(db, laboratorio="Operaciones Unitarias")

    codigos = [r.codigo for r in db.query(RegistroDB).all()]
    assert len(set(codigos)) == 3
    assert all(c.startswith("13082026") for c in codigos)


def test_el_codigo_legible_sigue_el_formato_oficial(db):
    declaracion = _persistir(db, fecha="2026-08-13", estado_fisico="Líquido")

    assert declaracion.codigo_formato == "13082026-LIQUID-001"


def test_el_codigo_legible_se_numera_dentro_del_registro(db):
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    registro = _abrir_registro(db)
    codigos = []
    for insumo in ["acetona", "etanol", "hexano"]:
        entrada = _entrada(insumos=[insumo], fecha="2026-08-13")
        declaracion = crear_declaracion(
            db, entrada, clasificar_residuo(entrada), registro=registro
        )
        codigos.append(declaracion.codigo_formato)

    assert codigos == ["13082026-LIQUID-001", "13082026-LIQUID-002", "13082026-LIQUID-003"]


def test_el_codigo_legible_refleja_el_estado_fisico(db):
    solido = _persistir(db, fecha="2026-08-13", estado_fisico="Sólido", es_punzocortante=True)

    assert "SOLIDO" in solido.codigo_formato


def test_el_identificador_del_residuo_es_unico_y_con_formato(db):
    primera = _persistir(db, fecha="2026-08-13", insumos=["acetona"])
    segunda = _persistir(db, fecha="2026-08-13", insumos=["etanol"])

    assert primera.codigo_residuo != segunda.codigo_residuo
    assert primera.codigo_residuo.startswith("13082026")
    assert primera.codigo_residuo.endswith("-ALVA")


def test_el_resultado_devuelve_el_codigo_definitivo(db):
    """El cliente debe recibir el código que quedó guardado, no uno provisional."""
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    entrada = _entrada(fecha="2026-08-13")
    resultado = clasificar_residuo(entrada)
    provisional = resultado.id_residuo

    declaracion = crear_declaracion(db, entrada, resultado)

    assert resultado.id_residuo == declaracion.codigo_residuo
    assert resultado.id_residuo != provisional


# --------------------------------------------------------------------------
# Consultas
# --------------------------------------------------------------------------

def test_el_historial_filtra_por_laboratorio_a_traves_del_registro(db):
    from core.repositorio import filtrar_declaraciones

    _persistir(db, fecha="2026-08-13", laboratorio="Química General")
    _persistir(db, fecha="2026-08-13", laboratorio="Química Analítica")

    _, general = filtrar_declaraciones(db, laboratorio="Química General")
    _, fantasma = filtrar_declaraciones(db, laboratorio="Inexistente")

    assert general == 1
    assert fantasma == 0


def test_filtrar_registros_por_periodo_y_laboratorio(db):
    from core.repositorio import filtrar_registros

    _abrir_registro(db, fecha=date(2026, 8, 13))
    _abrir_registro(db, fecha=date(2026, 9, 1), laboratorio="Química Analítica")

    _, agosto = filtrar_registros(db, mes=8, anio=2026)
    _, quimica = filtrar_registros(db, laboratorio="Química Analítica")
    _, todos = filtrar_registros(db)

    assert agosto == 1
    assert quimica == 1
    assert todos == 2
