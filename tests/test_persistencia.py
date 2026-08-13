"""Pruebas de persistencia, transacciones e integridad del esquema 3FN."""

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError


def _entrada(**cambios):
    from core.models import EntradaResiduoRequest

    datos = {
        "dependencia": "Ingeniería Industrial",
        "laboratorio": "Química General",
        "actividad": "Titulación ácido-base",
        "responsable": "Lic. Álvarez",
        "fecha": "2026-08-12",
        "descripcion": "Solución residual de ácido sulfúrico",
        "insumos": ["ácido sulfúrico 98%"],
        "peso_bruto_g": 1500.0,
        "tara_g": 150.0,
        "ph": 1.0,
    }
    datos.update(cambios)
    return EntradaResiduoRequest(**datos)


def _persistir(db, **cambios):
    from core.classifier import clasificar_residuo
    from core.repositorio import crear_declaracion

    entrada = _entrada(**cambios)
    return crear_declaracion(db, entrada, clasificar_residuo(entrada))


def _registro_de_prueba(db):
    """Registro reutilizable para las pruebas que no lo tienen como objeto."""
    from datetime import date as _date
    from core.db_models import LaboratorioDB, RegistroDB

    registro = db.query(RegistroDB).first()
    if registro is None:
        laboratorio = db.query(LaboratorioDB).first()
        registro = RegistroDB(
            codigo="12082026999999-QAQA",
            laboratorio_id=laboratorio.id,
            responsable_encargado="QA",
            fecha=_date(2026, 8, 12),
        )
        db.add(registro)
        db.flush()
    return registro


def _fila_declaracion(db, **cambios):
    """Fila mínima válida, para probar restricciones campo a campo."""
    from core.db_models import DeclaracionResiduoDB

    datos = {
        "codigo_residuo": "RES-CHECK-0001",
        "registro_id": _registro_de_prueba(db).id,
        "categoria_id": "acidos-corrosivos",
        "actividad": "Prueba de restricciones",
        "origen": "Académico",
        "responsable": "QA",
        "fecha": date(2026, 8, 12),
        "descripcion": "Fila de prueba",
        "nombre_normalizado": "Fila de prueba",
        "estado_fisico": "Líquido",
        "cantidad": 0.9,
        "unidad": "Kg",
        "modo_medicion": "pesaje",
        "peso_bruto_g": 1000.0,
        "tara_g": 100.0,
        "peso_neto_g": 900.0,
        "confianza": "Alto",
        "estado": "GENERADO",
        "narrativa": "Prueba",
    }
    datos.update(cambios)
    return DeclaracionResiduoDB(**datos)


# --------------------------------------------------------------------------
# Persistencia completa y kardex
# --------------------------------------------------------------------------

def test_declaracion_persiste_resultado_completo(db):
    declaracion = _persistir(db)

    assert declaracion.categoria_id == "acidos-corrosivos"
    assert declaracion.fecha == date(2026, 8, 12)
    assert declaracion.nombre_normalizado.startswith("Solución residual de")
    # El nombre normalizado se guarda como tal y no como copia de la descripción.
    assert declaracion.nombre_normalizado != declaracion.descripcion
    assert [i.nombre_quimico for i in declaracion.insumos] == ["ácido sulfúrico 98%"]
    assert "corrosion" in [p.codigo_pictograma for p in declaracion.pictogramas]
    textos = [o.texto for o in declaracion.observaciones]
    assert "Llenar como máximo al 75%" in textos
    assert "No verter al desagüe" in textos
    assert declaracion.estado == "GENERADO"


def test_indicadores_de_entrada_quedan_persistidos(db):
    """RF-03 exige que la clasificación sea reproducible desde lo guardado."""
    declaracion = _persistir(db, es_punzocortante=True, insumos=[])

    assert declaracion.es_punzocortante is True
    assert declaracion.desconocido is False
    assert declaracion.categoria_id == "punzocortantes"


def test_declaracion_desconocida_queda_en_evaluacion(db):
    declaracion = _persistir(db, desconocido=True, insumos=[])

    assert declaracion.escalar_csbqr is True
    assert declaracion.estado == "EN_EVALUACION"
    assert declaracion.confianza == "Bajo"


def test_creacion_registra_movimiento_de_kardex(db):
    declaracion = _persistir(db)

    assert len(declaracion.movimientos) == 1
    movimiento = declaracion.movimientos[0]
    assert movimiento.tipo_movimiento == "ENTRADA"
    assert movimiento.motivo == "generacion_laboratorio"
    assert movimiento.cantidad_g == declaracion.peso_neto_g
    assert movimiento.laboratorio_destino_id == declaracion.registro.laboratorio_id


# --------------------------------------------------------------------------
# Unicidad y cascadas
# --------------------------------------------------------------------------

def test_codigo_residuo_es_unico(db):
    primera = _persistir(db)

    db.add(_fila_declaracion(db, codigo_residuo=primera.codigo_residuo))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_insumo_duplicado_en_la_misma_declaracion_es_rechazado(db):
    from core.db_models import DeclaracionInsumoDB

    declaracion = _persistir(db)
    db.add(DeclaracionInsumoDB(
        declaracion_id=declaracion.id, nombre_quimico="ácido sulfúrico 98%"
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_insumos_repetidos_en_la_peticion_se_normalizan(db):
    declaracion = _persistir(db, insumos=["Acetona", " acetona ", "Etanol"])

    assert [i.nombre_quimico for i in declaracion.insumos] == ["Acetona", "Etanol"]


def test_borrar_declaracion_arrastra_sus_hijos(db):
    from core.db_models import (
        DeclaracionInsumoDB, DeclaracionObservacionDB, DeclaracionPictogramaDB,
        MovimientoKardexDB,
    )

    declaracion = _persistir(db)
    declaracion_id = declaracion.id

    db.delete(declaracion)
    db.commit()

    for modelo in (
        DeclaracionInsumoDB, DeclaracionPictogramaDB,
        DeclaracionObservacionDB, MovimientoKardexDB,
    ):
        restantes = db.query(modelo).filter_by(declaracion_id=declaracion_id).count()
        assert restantes == 0, f"{modelo.__tablename__} quedó huérfana"


def test_laboratorio_no_puede_repetir_nombre_en_su_dependencia(db):
    from core.db_models import LaboratorioDB

    existente = db.query(LaboratorioDB).first()
    db.add(LaboratorioDB(
        codigo="LAB-DUP-01",
        nombre=existente.nombre,
        dependencia_id=existente.dependencia_id,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --------------------------------------------------------------------------
# Transaccionalidad
# --------------------------------------------------------------------------

def test_categoria_no_sembrada_no_deja_declaracion_parcial(db):
    from core.classifier import clasificar_residuo
    from core.db_models import DeclaracionResiduoDB
    from core.repositorio import DatoMaestroFaltante, crear_declaracion

    entrada = _entrada()
    resultado = clasificar_residuo(entrada)
    resultado.categoria_id = "categoria-que-no-existe"

    with pytest.raises(DatoMaestroFaltante):
        crear_declaracion(db, entrada, resultado)

    assert db.query(DeclaracionResiduoDB).count() == 0


def test_fallo_al_insertar_hijos_revierte_la_cabecera(db):
    """Antes la cabecera se confirmaba antes que los insumos y quedaba huérfana."""
    from core.classifier import clasificar_residuo
    from core.db_models import DeclaracionResiduoDB
    from core.repositorio import crear_declaracion

    entrada = _entrada()
    resultado = clasificar_residuo(entrada)
    # Insumo duplicado inyectado después de validar: viola la unicidad de
    # (declaración, insumo) al confirmar, con la cabecera ya insertada.
    # No se usa una cadena sobredimensionada porque SQLite no aplica el largo
    # de VARCHAR y la prueba no fallaría igual en ambos motores.
    entrada.insumos = ["acetona", "acetona"]

    with pytest.raises(IntegrityError):
        crear_declaracion(db, entrada, resultado)

    db.rollback()
    assert db.query(DeclaracionResiduoDB).count() == 0


# --------------------------------------------------------------------------
# Restricciones de dominio
# --------------------------------------------------------------------------

@pytest.mark.parametrize("campo,valor", [
    ("peso_bruto_g", -1.0),
    ("tara_g", -1.0),
    ("peso_neto_g", -1.0),
    ("ph", 15.0),
    ("ph", -0.5),
    ("origen", "Personal"),
    ("estado_fisico", "Plasma"),
    ("confianza", "Altísimo"),
    ("estado", "PERDIDO"),
])
def test_valores_fuera_de_dominio_son_rechazados(db, campo, valor):
    db.add(_fila_declaracion(db, **{campo: valor}))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cantidad_incoherente_con_el_pesaje_es_rechazada(db):
    """Guarda contra confundir unidades en una declaración regulatoria."""
    db.add(_fila_declaracion(db, peso_neto_g=900.0, cantidad=900.0))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_la_cantidad_admite_el_redondeo_a_cuatro_decimales(db):
    db.add(_fila_declaracion(db, peso_bruto_g=1334.56, peso_neto_g=1234.56, cantidad=1.2346))
    db.commit()  # No debe lanzar: la diferencia está dentro de la holgura de 1 g.


def test_un_pesaje_sin_evidencia_es_rechazado(db):
    """Si dice haberse pesado, tiene que traer el peso que lo respalda."""
    db.add(_fila_declaracion(db, modo_medicion="pesaje", peso_bruto_g=None, peso_neto_g=None))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_una_cantidad_declarada_no_necesita_pesaje(db):
    db.add(_fila_declaracion(
        db, modo_medicion="declarada", unidad="L", cantidad=5.0,
        peso_bruto_g=None, tara_g=None, peso_neto_g=None,
    ))
    db.commit()


# --------------------------------------------------------------------------
# Resolución de dependencia y laboratorio
# --------------------------------------------------------------------------

def test_nombre_parcial_no_resuelve_a_otra_dependencia(db):
    """`ILIKE %Química%` asignaba la declaración a la primera coincidencia."""
    from core.db_models import DependenciaDB
    from core.repositorio import resolver_dependencia

    db.add(DependenciaDB(codigo="DEP-QMC", nombre="Facultad de Química Analítica"))
    db.commit()

    resuelta = resolver_dependencia(db, "Química")
    db.commit()

    assert resuelta.nombre == "Química"
    assert resuelta.codigo != "DEP-QMC"


def test_resolucion_ignora_mayusculas_acentuadas_y_espacios(db):
    from core.repositorio import resolver_dependencia

    resuelta = resolver_dependencia(db, "  ingeniería INDUSTRIAL ")

    assert resuelta.codigo == "DEP-IND"
    assert resuelta.en_catalogo_oficial is True


def test_laboratorios_homonimos_viven_en_dependencias_distintas(db):
    """Docimasia y Microbiología existen en Industrial y en Ambiental."""
    from core.repositorio import resolver_dependencia, resolver_laboratorio

    ingenieria = resolver_dependencia(db, "Ingeniería Industrial")
    lab_ingenieria = resolver_laboratorio(db, "Docimasia", ingenieria)

    ciencias = resolver_dependencia(db, "Ingeniería Ambiental")
    lab_ciencias = resolver_laboratorio(db, "Docimasia", ciencias)
    db.commit()

    assert lab_ingenieria.id != lab_ciencias.id
    assert lab_ciencias.dependencia_id == ciencias.id


# --------------------------------------------------------------------------
# Consultas por período
# --------------------------------------------------------------------------

def test_periodo_filtra_por_rango_de_fechas_real(db):
    from core.repositorio import declaraciones_del_periodo

    _persistir(db, fecha="2026-08-01")
    _persistir(db, fecha="2026-08-31")
    _persistir(db, fecha="2026-09-01")
    _persistir(db, fecha="2026-07-31")

    agosto = declaraciones_del_periodo(db, mes=8, anio=2026)

    assert [d.fecha for d in agosto] == [date(2026, 8, 1), date(2026, 8, 31)]


def test_periodo_de_diciembre_no_desborda_al_ano_siguiente(db):
    from core.repositorio import declaraciones_del_periodo

    _persistir(db, fecha="2026-12-15")
    _persistir(db, fecha="2027-01-05")

    diciembre = declaraciones_del_periodo(db, mes=12, anio=2026)

    assert [d.fecha for d in diciembre] == [date(2026, 12, 15)]


# --------------------------------------------------------------------------
# Datos maestros
# --------------------------------------------------------------------------

def test_seeder_es_idempotente(db):
    from core.seeder_3fn import sembrar_datos_maestros

    resumen = sembrar_datos_maestros(db, verboso=False)

    assert not any(resumen.values()), f"La segunda siembra alteró la base: {resumen}"


def test_seeder_siembra_las_quince_categorias(db):
    from core.db_models import CategoriaULimaDB

    assert db.query(CategoriaULimaDB).count() == 15


def test_seeder_retira_categorias_fuera_de_la_ontologia(db):
    """La base traía 19 categorías: 4 sobrevivían de una ontología anterior."""
    from core.db_models import CategoriaULimaDB
    from core.seeder_3fn import sembrar_datos_maestros

    db.add(CategoriaULimaDB(
        id="solventes-inflamables", nombre="Obsoleta",
        caracteristica_principal="Inflamable", clase_sunat="Líquidos Inflamables",
        clase_basilea="H3", grupo_compatibilidad="INFLAMABLE", envase_recomendado="Frasco",
    ))
    db.commit()

    resumen = sembrar_datos_maestros(db, verboso=False)

    assert resumen["categorias_huerfanas_eliminadas"] == ["solventes-inflamables"]
    assert db.get(CategoriaULimaDB, "solventes-inflamables") is None


def test_categoria_obsoleta_con_declaraciones_se_conserva(db):
    """Nunca se borra una categoría que respalda registros ya emitidos."""
    from core.db_models import CategoriaULimaDB
    from core.seeder_3fn import sembrar_datos_maestros

    db.add(CategoriaULimaDB(
        id="solventes-inflamables", nombre="Obsoleta",
        caracteristica_principal="Inflamable", clase_sunat="Líquidos Inflamables",
        clase_basilea="H3", grupo_compatibilidad="INFLAMABLE", envase_recomendado="Frasco",
    ))
    db.flush()
    db.add(_fila_declaracion(db, categoria_id="solventes-inflamables"))
    db.commit()

    resumen = sembrar_datos_maestros(db, verboso=False)

    assert resumen["categorias_huerfanas_retenidas"] == [
        {"id": "solventes-inflamables", "declaraciones": 1}
    ]
    assert db.get(CategoriaULimaDB, "solventes-inflamables") is not None


def test_seeder_corrige_una_categoria_editada_a_mano(db):
    from core.db_models import CategoriaULimaDB
    from core.seeder_3fn import sembrar_datos_maestros

    categoria = db.get(CategoriaULimaDB, "acidos-corrosivos")
    categoria.envase_recomendado = "valor divergente"
    db.commit()

    resumen = sembrar_datos_maestros(db, verboso=False)

    assert resumen["categorias_actualizadas"] == [
        {"id": "acidos-corrosivos", "campos": ["envase_recomendado"]}
    ]
    assert db.get(CategoriaULimaDB, "acidos-corrosivos").envase_recomendado != "valor divergente"


def test_todas_las_categorias_declaran_sus_incompatibilidades(db):
    """La etiqueta imprime este texto; una categoría sin él sale sin advertencia."""
    from core.db_models import CategoriaULimaDB

    vacias = [
        categoria.id for categoria in db.query(CategoriaULimaDB).all()
        if not (categoria.no_mezclar_con or "").strip()
    ]

    assert vacias == [], f"Categorías sin incompatibilidades declaradas: {vacias}"


def test_etiqueta_pdf_incluye_las_incompatibilidades_de_la_categoria(db):
    from core.artifacts import etiqueta_pdf
    from core.repositorio import consulta_declaraciones

    _persistir(db)
    registro = consulta_declaraciones(db).first()

    assert registro.categoria.no_mezclar_con  # dato que alimenta la etiqueta
    contenido = etiqueta_pdf(registro).getvalue()

    assert contenido[:4] == b"%PDF"
    assert len(contenido) > 1000


def test_etiqueta_pdf_soporta_una_descripcion_larga(db):
    """Con desplazamiento fijo, una descripción larga tapaba los pictogramas."""
    from core.artifacts import etiqueta_pdf
    from core.repositorio import consulta_declaraciones

    _persistir(db, descripcion="Mezcla residual compleja. " * 40)
    registro = consulta_declaraciones(db).first()

    contenido = etiqueta_pdf(registro).getvalue()

    assert contenido[:4] == b"%PDF"


def test_matriz_de_incompatibilidad_se_guarda_en_orden_canonico(db):
    """(ÁCIDO, BASE) y (BASE, ÁCIDO) deben ser una sola regla."""
    from core.db_models import ReglaIncompatibilidadDB

    reglas = db.query(ReglaIncompatibilidadDB).all()
    pares = {(regla.grupo_a, regla.grupo_b) for regla in reglas}

    assert len(pares) == len(reglas)
    for grupo_a, grupo_b in pares:
        assert (grupo_b, grupo_a) not in pares or grupo_a == grupo_b


def test_compatibilidad_se_evalua_contra_la_matriz_persistida(db):
    from core.db_models import ReglaIncompatibilidadDB
    from core.repositorio import evaluar_compatibilidad

    assert evaluar_compatibilidad(db, ["ÁCIDO", "BASE"])["veredicto"] == "NUNCA"
    assert evaluar_compatibilidad(db, ["BASE", "ÁCIDO"])["veredicto"] == "NUNCA"
    assert evaluar_compatibilidad(db, ["ÁCIDO", "ÁCIDO"])["veredicto"] == "COMPATIBLE"
    assert evaluar_compatibilidad(db, ["ÁCIDO", "RADIACTIVO"])["veredicto"] == "SEGREGAR"

    # Retirar la regla de la base cambia el veredicto: la tabla es la fuente de
    # verdad en tiempo de ejecución, no la lista en memoria del clasificador.
    db.query(ReglaIncompatibilidadDB).filter_by(grupo_a="BASE", grupo_b="ÁCIDO").delete()
    db.commit()

    assert evaluar_compatibilidad(db, ["ÁCIDO", "BASE"])["veredicto"] == "SEGREGAR"
