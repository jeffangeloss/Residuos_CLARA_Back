"""
Seeder para Cargar Datos Maestros en el Esquema 3FN de PostgreSQL
Plataforma CLARA+ - Universidad de Lima

El seeder es la única fuente de datos maestros: reconcilia el contenido de la
base con la ontología y la matriz declaradas en `core/classifier.py`. Es
idempotente y convergente, es decir, corregir la ontología y volver a ejecutarlo
deja la base en el estado correcto sin intervención manual.
"""

from typing import Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.db_models import (
    CategoriaULimaDB, DeclaracionResiduoDB, DependenciaDB, LaboratorioDB,
    ReglaIncompatibilidadDB, TipoEnvaseDB,
)
from core.catalogos import (
    DEPENDENCIAS_OFICIALES, LABORATORIOS_OFICIALES, TIPOS_ENVASE_OFICIALES,
)
from core.classifier import MATRIZ_CSBQR, ONTOLOGIA, PARES_SIN_GRUPO_ASIGNADO

CAMPOS_CATEGORIA = (
    "nombre",
    "caracteristica_principal",
    "caracteristica_declaracion",
    "clase_sunat",
    "clase_basilea",
    "grupo_compatibilidad",
    "envase_recomendado",
    "no_mezclar_con",
)

CATEGORIAS_MAESTRAS = [
    {
        "id": categoria_id,
        "nombre": categoria["nombre"],
        "caracteristica_principal": categoria["caracteristica"],
        "caracteristica_declaracion": categoria["caracteristicaDeclaracion"],
        "clase_sunat": categoria["declaracion"],
        "clase_basilea": categoria["basilea"],
        "grupo_compatibilidad": categoria["grupo"],
        "envase_recomendado": categoria["envase"],
        # Texto literal del Gem; es el que se imprime en la etiqueta.
        "no_mezclar_con": categoria["noAlmacenarConTexto"][:300],
    }
    for categoria_id, categoria in ONTOLOGIA.items()
]


def par_canonico(grupo_a: str, grupo_b: str) -> Tuple[str, str]:
    """Ordena un par de grupos de forma determinista.

    La matriz de incompatibilidad es simétrica: (ÁCIDO, BASE) y (BASE, ÁCIDO)
    son la misma regla. El orden se fija en Python, por puntos de código, y no
    con una restricción SQL, porque la comparación de cadenas acentuadas depende
    de la colación y ordenaría distinto en SQLite que en PostgreSQL.
    """
    return tuple(sorted((grupo_a, grupo_b)))


# La matriz completa del CSBQR: los tres veredictos, incluida la diagonal.
# Antes solo se sembraban los pares "NUNCA" y todo lo demás se derivaba en
# tiempo de ejecución, lo que dejaba 24 combinaciones peligrosas como SEGREGAR.
REGLAS_INCOMPATIBILIDAD_MAESTRAS = [
    (*par_canonico(grupo_a, grupo_b), veredicto, razon)
    for (grupo_a, grupo_b), (veredicto, razon) in MATRIZ_CSBQR.items()
] + [
    # Pares del CSBQR cuyos grupos aún no existen en la ontología. Se siembran
    # para no perder el criterio, aunque hoy ninguna categoría los produce.
    (*par_canonico(grupo_a, grupo_b), "NUNCA", razon)
    for grupo_a, grupo_b, razon in PARES_SIN_GRUPO_ASIGNADO
]


def _sembrar_catalogo_institucional(db: Session, resumen: Dict) -> None:
    """Siembra las dependencias y laboratorios del formato 2026.

    No borra lo que no esté en el catálogo: 29 de los 101 registros históricos
    usan laboratorios que el formato no lista, y retirarlos dejaría esas
    declaraciones sin ubicación. Lo que hace es marcarlos como oficiales o no,
    para que la diferencia sea visible.
    """
    por_nombre = {}
    for codigo, nombre, token in DEPENDENCIAS_OFICIALES:
        dependencia = db.query(DependenciaDB).filter_by(nombre=nombre).first()
        if not dependencia:
            dependencia = DependenciaDB(
                codigo=codigo, nombre=nombre, token_formato=token, en_catalogo_oficial=True
            )
            db.add(dependencia)
            db.flush()
            resumen["dependencias_creadas"].append(nombre)
        elif not dependencia.en_catalogo_oficial or dependencia.token_formato != token:
            dependencia.token_formato = token
            dependencia.en_catalogo_oficial = True
            resumen["dependencias_actualizadas"].append(nombre)
        por_nombre[nombre] = dependencia

    for nombre_dependencia, laboratorios in LABORATORIOS_OFICIALES.items():
        dependencia = por_nombre[nombre_dependencia]
        for orden, nombre_lab in enumerate(laboratorios, start=1):
            laboratorio = (
                db.query(LaboratorioDB)
                .filter_by(dependencia_id=dependencia.id, nombre=nombre_lab)
                .first()
            )
            if not laboratorio:
                db.add(LaboratorioDB(
                    codigo=f"{dependencia.codigo.replace('DEP-', 'LAB-')}-{orden:02d}",
                    nombre=nombre_lab,
                    dependencia_id=dependencia.id,
                    en_catalogo_oficial=True,
                ))
                resumen["laboratorios_creados"].append(f"{nombre_dependencia}/{nombre_lab}")
            elif not laboratorio.en_catalogo_oficial:
                laboratorio.en_catalogo_oficial = True
                resumen["laboratorios_actualizados"].append(f"{nombre_dependencia}/{nombre_lab}")

    db.flush()


def _sembrar_tipos_envase(db: Session, resumen: Dict) -> None:
    """Siembra el catálogo de envases normalizado."""
    for codigo, nombre in TIPOS_ENVASE_OFICIALES:
        tipo = db.query(TipoEnvaseDB).filter_by(codigo=codigo).first()
        if not tipo:
            db.add(TipoEnvaseDB(codigo=codigo, nombre=nombre))
            resumen["envases_creados"].append(nombre)
        elif tipo.nombre != nombre:
            tipo.nombre = nombre
            resumen["envases_actualizados"].append(nombre)
    db.flush()


def _sembrar_categorias(db: Session, resumen: Dict) -> None:
    """Inserta o actualiza las categorías para que coincidan con la ontología."""
    for datos in CATEGORIAS_MAESTRAS:
        categoria = db.query(CategoriaULimaDB).filter_by(id=datos["id"]).first()
        if not categoria:
            db.add(CategoriaULimaDB(**datos))
            resumen["categorias_creadas"].append(datos["id"])
            continue

        # Convergencia: si la ontología cambió un envase o un código Basilea, la
        # fila existente debe adoptarlo. La versión anterior solo insertaba las
        # ausentes, así que una corrección de dominio nunca llegaba a la base.
        cambios = [
            campo for campo in CAMPOS_CATEGORIA
            if getattr(categoria, campo) != datos[campo]
        ]
        if cambios:
            for campo in cambios:
                setattr(categoria, campo, datos[campo])
            resumen["categorias_actualizadas"].append({"id": datos["id"], "campos": cambios})

    db.flush()


def _reconciliar_categorias_huerfanas(db: Session, resumen: Dict) -> None:
    """Retira categorías que ya no existen en la ontología vigente.

    Solo se eliminan las que ninguna declaración referencia. Si una categoría
    obsoleta tiene declaraciones asociadas se conserva y se reporta, porque
    borrarla destruiría registros regulatorios ya emitidos.
    """
    ids_vigentes = {datos["id"] for datos in CATEGORIAS_MAESTRAS}
    huerfanas = [
        categoria for categoria in db.query(CategoriaULimaDB).all()
        if categoria.id not in ids_vigentes
    ]

    for categoria in huerfanas:
        referencias = (
            db.query(func.count(DeclaracionResiduoDB.id))
            .filter(DeclaracionResiduoDB.categoria_id == categoria.id)
            .scalar()
        )
        if referencias:
            resumen["categorias_huerfanas_retenidas"].append(
                {"id": categoria.id, "declaraciones": referencias}
            )
        else:
            db.delete(categoria)
            resumen["categorias_huerfanas_eliminadas"].append(categoria.id)

    db.flush()


def _sembrar_reglas(db: Session, resumen: Dict) -> None:
    """Inserta, actualiza y retira reglas para reflejar la matriz CSBQR vigente."""
    vigentes = set()
    for grupo_a, grupo_b, veredicto, razon in REGLAS_INCOMPATIBILIDAD_MAESTRAS:
        vigentes.add((grupo_a, grupo_b))
        regla = db.query(ReglaIncompatibilidadDB).filter_by(grupo_a=grupo_a, grupo_b=grupo_b).first()
        if not regla:
            db.add(ReglaIncompatibilidadDB(
                grupo_a=grupo_a, grupo_b=grupo_b,
                veredicto=veredicto, explicacion_riesgo=razon,
            ))
            resumen["reglas_creadas"].append(f"{grupo_a}+{grupo_b}={veredicto}")
        elif regla.veredicto != veredicto or regla.explicacion_riesgo != razon:
            regla.veredicto = veredicto
            regla.explicacion_riesgo = razon
            resumen["reglas_actualizadas"].append(f"{grupo_a}+{grupo_b}={veredicto}")

    # Una regla que ya no está en la matriz debe desaparecer: dejarla vigente
    # significaría evaluar el acopio con un criterio retirado.
    for regla in db.query(ReglaIncompatibilidadDB).all():
        if (regla.grupo_a, regla.grupo_b) not in vigentes:
            resumen["reglas_retiradas"].append(f"{regla.grupo_a}+{regla.grupo_b}")
            db.delete(regla)

    db.flush()


def sembrar_datos_maestros(db: Session, verboso: bool = True) -> Dict[str, List]:
    """Reconcilia dependencias, laboratorios, categorías y reglas maestras.

    Devuelve un resumen de lo que cambió, de modo que el arranque del servicio y
    las pruebas puedan verificar que la operación es realmente idempotente.
    """
    resumen: Dict[str, List] = {
        "dependencias_creadas": [],
        "dependencias_actualizadas": [],
        "laboratorios_creados": [],
        "laboratorios_actualizados": [],
        "envases_creados": [],
        "envases_actualizados": [],
        "categorias_creadas": [],
        "categorias_actualizadas": [],
        "categorias_huerfanas_eliminadas": [],
        "categorias_huerfanas_retenidas": [],
        "reglas_creadas": [],
        "reglas_actualizadas": [],
        "reglas_retiradas": [],
    }

    try:
        _sembrar_catalogo_institucional(db, resumen)
        _sembrar_tipos_envase(db, resumen)
        _sembrar_categorias(db, resumen)
        _reconciliar_categorias_huerfanas(db, resumen)
        _sembrar_reglas(db, resumen)
        db.commit()
    except Exception:
        db.rollback()
        raise

    if verboso:
        _reportar(resumen)

    return resumen


def _reportar(resumen: Dict[str, List]) -> None:
    if not any(resumen.values()):
        print("✅ Datos maestros ya sincronizados con la ontología vigente.")
        return

    for clave, elementos in resumen.items():
        if elementos:
            print(f"   • {clave.replace('_', ' ')}: {len(elementos)} → {elementos}")

    if resumen["categorias_huerfanas_retenidas"]:
        print(
            "⚠️ Hay categorías fuera de la ontología con declaraciones asociadas. "
            "Requieren decisión del responsable de dominio antes de retirarlas."
        )
