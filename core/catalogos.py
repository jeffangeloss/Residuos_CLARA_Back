"""Catálogos institucionales de CLARA+.

Las dependencias y los laboratorios provienen de la hoja `Listas` del
`Formato-Declaración de residuos peligrosos generados-2026.xlsx` y del
formulario de declaración. Los tipos de envase se derivan de normalizar las 50
variantes que aparecen en la base histórica.

**El catálogo no es cerrado.** 29 de los 101 registros históricos usan
laboratorios que el formato 2026 no lista —Tópico, Química Industrial,
Termodinámica, entre otros—, así que impedir lo que no esté aquí bloquearía
declaraciones legítimas. Lo que sí se hace es marcar qué entradas son oficiales,
para que la interfaz las ofrezca primero y para que las que se creen sobre la
marcha queden visibles al CSBQR.
"""

import unicodedata
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Dependencias y laboratorios
# ---------------------------------------------------------------------------
#
# El nombre visible usa espacios; el token es como lo escribe el formato oficial
# en su desplegable, con guiones bajos y sin la preposición.
DEPENDENCIAS_OFICIALES: List[Tuple[str, str, str]] = [
    # (código, nombre visible, token del formato)
    ("DEP-IND", "Ingeniería Industrial", "Ingeniería_Industrial"),
    ("DEP-CIV", "Ingeniería Civil", "Ingeniería_Civil"),
    ("DEP-SIS", "Ingeniería de Sistemas", "Ingeniería_Sistemas"),
    ("DEP-AMB", "Ingeniería Ambiental", "Ingeniería_Ambiental"),
    ("DEP-MEC", "Ingeniería Mecatrónica", "Ingeniería_Mecatrónica"),
    ("DEP-MED", "Departamento Médico", "Departamento_Médico"),
    ("DEP-MAN", "Departamento de Mantenimiento", "Departamento_Mantenimiento"),
]

LABORATORIOS_OFICIALES: Dict[str, List[str]] = {
    "Ingeniería Industrial": [
        "Alimentos Funcionales",
        "Química Analítica",
        "Manufactura FABLAB",
        "Docimasia",
        "Química General",
        "Smart Factory",
        "Microbiología",
        "Calidad, Metrología y Materiales",
        "Máquinas e Instrumentos",
        "Nanotecnología",
        "Operaciones Unitarias (OPU)",
        "Diseño de Instalaciones",
        "Física e Ingeniería Electrica",
        "Confecciones",
    ],
    "Ingeniería Civil": [
        "Estructuras",
        "Pavimentos",
        "Geotecnia",
        "Simulación de Proyectos",
        "Ingeniería Ambiental",
        "Topografía y Geomática",
        "Hidráulica",
        "Materiales",
    ],
    "Ingeniería de Sistemas": [
        "Redes y Ciberseguridad",
        "Soporte Tecnológico",
        "Internet de las Cosas",
        "Aprendizaje en Tecnologías de la Información (IT LAB)",
        "Virtualización y Computación en la Nube",
        "SAP Next-Gen",
        "Computación de Alto Rendimiento",
        "Inteligencia Artificial",
    ],
    # Docimasia, Microbiología y Nanotecnología existen también en Industrial.
    # Son laboratorios homónimos en dependencias distintas, por eso la unicidad
    # del nombre es por dependencia y no global.
    "Ingeniería Ambiental": [
        "Docimasia",
        "Microbiología",
        "Nanotecnología",
    ],
    "Ingeniería Mecatrónica": [
        "Manufactura Flexible - CIM",
    ],
    "Departamento Médico": ["Otros"],
    "Departamento de Mantenimiento": ["Otros"],
}


# ---------------------------------------------------------------------------
# Tipos de envase
# ---------------------------------------------------------------------------
#
# La base histórica trae 50 variantes para unos pocos conceptos: "Plástico",
# "Envase de plástico", "Envase De Plástico", "Plastico" y "Envase de plástico
# N°1" son lo mismo escrito de cinco maneras.
TIPOS_ENVASE_OFICIALES: List[Tuple[str, str]] = [
    # (código, nombre visible)
    ("ENV-PLA", "Envase de plástico"),
    ("ENV-VID", "Envase de vidrio"),
    ("ENV-VAM", "Envase de vidrio ámbar"),
    ("ENV-BOL", "Bolsa de plástico"),
    ("ENV-CTP", "Contenedor de plástico"),
    ("ENV-CTV", "Contenedor de vidrio"),
    ("ENV-BOT", "Botella de plástico"),
    ("ENV-FRP", "Frasco de plástico"),
    ("ENV-BAL", "Balde de plástico"),
    ("ENV-GAL", "Galonera de plástico"),
    ("ENV-BID", "Bidón de plástico"),
    ("ENV-MET", "Envase metálico"),
    ("ENV-CAR", "Caja de cartón"),
    ("ENV-PZC", "Contenedor rígido para punzocortantes"),
]

# Reglas en orden de prioridad. Cada una es (alguna_de, todas_de, tipo):
# basta con que aparezca **alguna** palabra de la primera tupla, y además deben
# aparecer **todas** las de la segunda.
#
# El orden importa por dos motivos: la forma manda sobre el material —"Bolsa de
# plástico" es una bolsa antes que un plástico—, y el riesgo manda sobre la
# forma: una "Caja de cartón para objetos punzantes" es un contenedor de
# punzocortantes antes que una caja.
_REGLAS_ENVASE: List[Tuple[Tuple[str, ...], Tuple[str, ...], str]] = [
    (("punzocortante", "punzante"), (), "Contenedor rígido para punzocortantes"),
    (("carton",), (), "Caja de cartón"),
    (("bolsa", "ziploc"), (), "Bolsa de plástico"),
    (("balde",), (), "Balde de plástico"),
    (("galonera",), (), "Galonera de plástico"),
    (("bidon",), (), "Bidón de plástico"),
    (("lata", "metal"), (), "Envase metálico"),
    (("ambar", "oscuro"), (), "Envase de vidrio ámbar"),
    (("contenedor",), ("vidrio",), "Contenedor de vidrio"),
    (("contenedor",), (), "Contenedor de plástico"),
    (("botella",), (), "Botella de plástico"),
    (("frasco", "galon"), ("vidrio",), "Envase de vidrio"),
    (("frasco", "galon"), (), "Frasco de plástico"),
    (("vidrio",), (), "Envase de vidrio"),
    (("plastico",), (), "Envase de plástico"),
]


def _clave(texto: str) -> str:
    """Minúsculas sin acentos, para comparar sin depender de la escritura."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


def normalizar_tipo_envase(texto: str) -> Optional[str]:
    """Lleva una descripción libre de envase al tipo canónico que le corresponde.

    Devuelve None cuando el texto no permite decidir, en lugar de forzar una
    coincidencia: un envase mal clasificado es peor que uno sin clasificar.

        >>> normalizar_tipo_envase("Envase De Plástico")
        'Envase de plástico'
        >>> normalizar_tipo_envase("Frasco de Vidrio Oscuro")
        'Envase de vidrio ámbar'
        >>> normalizar_tipo_envase("Bolsa Ziploc con Cierre")
        'Bolsa de plástico'
    """
    if not texto or not texto.strip():
        return None

    clave = _clave(texto)
    for alguna_de, todas_de, canonico in _REGLAS_ENVASE:
        if any(t in clave for t in alguna_de) and all(t in clave for t in todas_de):
            return canonico
    return None


def dependencia_oficial(nombre: str) -> Optional[Tuple[str, str, str]]:
    """Busca una dependencia del catálogo por nombre o por token del formato."""
    objetivo = _clave(nombre)
    for entrada in DEPENDENCIAS_OFICIALES:
        if objetivo in (_clave(entrada[1]), _clave(entrada[2])):
            return entrada
    return None
