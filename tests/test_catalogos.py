"""Pruebas de los catálogos institucionales y del vocabulario del formato."""

import pytest


# --------------------------------------------------------------------------
# Dependencias y laboratorios
# --------------------------------------------------------------------------

def test_se_siembran_las_siete_dependencias_del_formato(db):
    from core.db_models import DependenciaDB

    oficiales = db.query(DependenciaDB).filter_by(en_catalogo_oficial=True).all()

    assert len(oficiales) == 7
    assert {d.nombre for d in oficiales} == {
        "Ingeniería Industrial", "Ingeniería Civil", "Ingeniería de Sistemas",
        "Ingeniería Ambiental", "Ingeniería Mecatrónica",
        "Departamento Médico", "Departamento de Mantenimiento",
    }


def test_cada_dependencia_conoce_su_token_del_formato(db):
    """El Excel escribe "Ingeniería_Sistemas", no "Ingeniería de Sistemas"."""
    from core.db_models import DependenciaDB

    sistemas = db.query(DependenciaDB).filter_by(nombre="Ingeniería de Sistemas").first()
    mantenimiento = db.query(DependenciaDB).filter_by(
        nombre="Departamento de Mantenimiento").first()

    assert sistemas.token_formato == "Ingeniería_Sistemas"
    assert mantenimiento.token_formato == "Departamento_Mantenimiento"


def test_se_siembran_los_laboratorios_agrupados_por_dependencia(db):
    from core.db_models import DependenciaDB, LaboratorioDB

    industrial = db.query(DependenciaDB).filter_by(nombre="Ingeniería Industrial").first()
    laboratorios = db.query(LaboratorioDB).filter_by(dependencia_id=industrial.id).all()

    assert len(laboratorios) == 14
    assert "Operaciones Unitarias (OPU)" in {l.nombre for l in laboratorios}


def test_hay_laboratorios_homonimos_en_dependencias_distintas(db):
    """Docimasia existe en Industrial y en Ambiental. Son laboratorios distintos."""
    from core.db_models import LaboratorioDB

    docimasias = db.query(LaboratorioDB).filter_by(nombre="Docimasia").all()

    assert len(docimasias) == 2
    assert len({l.dependencia_id for l in docimasias}) == 2


def test_el_catalogo_no_es_cerrado(db):
    """29 de 101 registros históricos usan laboratorios fuera del formato 2026.

    Bloquear lo que no esté en el catálogo impediría declarar residuos reales,
    así que se permite crearlos y se marcan como no oficiales.
    """
    from core.repositorio import resolver_dependencia, resolver_laboratorio

    industrial = resolver_dependencia(db, "Ingeniería Industrial")
    topico = resolver_laboratorio(db, "Química Industrial", industrial)
    db.commit()

    assert topico.id is not None
    assert topico.en_catalogo_oficial is False
    assert industrial.en_catalogo_oficial is True


def test_resolver_no_duplica_un_laboratorio_del_catalogo(db):
    from core.db_models import LaboratorioDB
    from core.repositorio import resolver_dependencia, resolver_laboratorio

    industrial = resolver_dependencia(db, "Ingeniería Industrial")
    antes = db.query(LaboratorioDB).filter_by(dependencia_id=industrial.id).count()

    resolver_laboratorio(db, "  química GENERAL ", industrial)
    db.commit()

    assert db.query(LaboratorioDB).filter_by(dependencia_id=industrial.id).count() == antes


# --------------------------------------------------------------------------
# Característica del formato oficial
# --------------------------------------------------------------------------

def test_cada_categoria_trae_la_caracteristica_del_desplegable(db):
    from core.db_models import CategoriaULimaDB
    from core.models import CaracteristicaDeclaracion, valores

    permitidas = set(valores(CaracteristicaDeclaracion))
    fuera = [
        (c.id, c.caracteristica_declaracion)
        for c in db.query(CategoriaULimaDB).all()
        if c.caracteristica_declaracion not in permitidas
    ]

    assert fuera == [], f"Valores que el Excel rechazaría: {fuera}"


@pytest.mark.parametrize("categoria,esperado", [
    ("acidos-corrosivos", "Corrosividad"),
    ("bases-corrosivas", "Corrosividad"),
    ("solventes-halogenados", "Toxicidad (+ inflamabilidad en algunos)"),
    ("metales-pesados", "Toxicidad (+ ecotoxicidad)"),
    ("aceites-contaminados", "Inflamabilidad (+ toxicidad)"),
    ("aerosoles", "Reactividad / inflamabilidad (por presión)"),
    ("punzocortantes", "Patogenicidad (o la del contaminante)"),
    ("envases-contaminados", "Heredada del contaminante"),
    ("solidos-contaminados", "Heredada del contaminante"),
    ("raee", "Toxicidad"),
    ("radiactivos", "Radioactividad"),
    ("no-identificados", "En evaluación"),
])
def test_mapeo_categoria_caracteristica_del_formato(db, categoria, esperado):
    """Tomado de la tabla D26:E39 de la hoja `Listas` del formato 2026."""
    from core.db_models import CategoriaULimaDB

    assert db.get(CategoriaULimaDB, categoria).caracteristica_declaracion == esperado


# --------------------------------------------------------------------------
# Tipos de envase
# --------------------------------------------------------------------------

def test_se_siembra_el_catalogo_de_envases(db):
    from core.db_models import TipoEnvaseDB

    assert db.query(TipoEnvaseDB).count() == 14


@pytest.mark.parametrize("texto,esperado", [
    # Las cinco formas de escribir lo mismo que hay en el histórico.
    ("Plástico", "Envase de plástico"),
    ("Plastico", "Envase de plástico"),
    ("Envase de plástico", "Envase de plástico"),
    ("Envase De Plástico", "Envase de plástico"),
    ("Envase de plástico N°1", "Envase de plástico"),
    # Vidrio y sus variantes ámbar.
    ("Vidrio", "Envase de vidrio"),
    ("Frasco de Vidrio", "Envase de vidrio"),
    ("Frasco de Vidrio Oscuro", "Envase de vidrio ámbar"),
    ("Botella Ámbar de Vidrio", "Envase de vidrio ámbar"),
    ("Envase de Vidrio Ámbar N°2", "Envase de vidrio ámbar"),
    # La forma manda sobre el material.
    ("Bolsa de plástico", "Bolsa de plástico"),
    ("Bolsa Ziploc con Cierre", "Bolsa de plástico"),
    ("Contenedor de Plástico", "Contenedor de plástico"),
    ("Contenedor de Vidrio", "Contenedor de vidrio"),
    ("Botella de plástico", "Botella de plástico"),
    ("Balde de Plástico", "Balde de plástico"),
    ("Galonera Plástico 3.7L", "Galonera de plástico"),
    ("Bidon de Plastico", "Bidón de plástico"),
    ("Frasco Plástico 500 mL", "Frasco de plástico"),
    # Metálicos.
    ("Lata", "Envase metálico"),
    ("Envase metálico", "Envase metálico"),
    ("Contenedor metálico", "Envase metálico"),
    # Del ejemplo del formato 2026.
    ("Caja de cartón para objetos punzantes", "Contenedor rígido para punzocortantes"),
])
def test_normalizacion_de_tipos_de_envase(texto, esperado):
    from core.catalogos import normalizar_tipo_envase

    assert normalizar_tipo_envase(texto) == esperado


def test_un_envase_indescifrable_no_se_fuerza():
    """Mejor sin clasificar que mal clasificado."""
    from core.catalogos import normalizar_tipo_envase

    assert normalizar_tipo_envase("") is None
    assert normalizar_tipo_envase("recipiente") is None


def test_toda_normalizacion_cae_en_el_catalogo_sembrado(db):
    from core.catalogos import TIPOS_ENVASE_OFICIALES, normalizar_tipo_envase, _REGLAS_ENVASE

    nombres = {nombre for _, nombre in TIPOS_ENVASE_OFICIALES}
    for _, _, canonico in _REGLAS_ENVASE:
        assert canonico in nombres, f"'{canonico}' no está en el catálogo sembrado"


# --------------------------------------------------------------------------
# Vocabulario de origen y estado físico
# --------------------------------------------------------------------------

def test_el_origen_otros_es_valido(db):
    """Lo contempla el formato y lo usan 7 registros históricos."""
    from tests.test_persistencia import _persistir

    declaracion = _persistir(db, origen="Otros")

    assert declaracion.origen == "Otros"


def test_gel_lodo_ya_no_es_un_estado_fisico():
    """No existe en el formulario, ni en el formato, ni en los 856 registros."""
    from pydantic import ValidationError
    from tests.test_persistencia import _entrada

    with pytest.raises(ValidationError):
        _entrada(estado_fisico="Gel / Lodo")


def test_la_base_tambien_rechaza_gel_lodo(db):
    from sqlalchemy.exc import IntegrityError
    from tests.test_persistencia import _fila_declaracion

    db.add(_fila_declaracion(db, estado_fisico="Gel / Lodo"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
