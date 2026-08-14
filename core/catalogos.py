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


# ---------------------------------------------------------------------------
# Padrón de personal
# ---------------------------------------------------------------------------
#
# Los dos formularios de Google recogían el correo automáticamente, pero en el
# Excel exportado esa columna está vacía en las 856 filas. Los nombres, en
# cambio, se escribieron a mano cada vez, y se multiplicaron: la misma persona
# aparece como "Javier Quino" y "Javier Quino Favero"; "Milagros Alvarado",
# "Milagros Alvarado Apaza" y "Milagros Ariana Alvarado Apaza"; "Nancy
# Chasquibol Silva" y "Nancy Chaquibol Silva", que además es un error de
# tipeo. Contarlas como personas distintas infla el padrón de 34 encargados
# reales a 34 cadenas de texto sin relación entre sí.
#
# Por eso cada persona trae sus variantes conocidas: el móvil ofrece el nombre
# canónico y la importación histórica de la Fase 11 puede resolver las 856
# filas contra este padrón en lugar de crear una persona por escritura.
#
# Los tres papeles no son excluyentes: Silvia Ponce firma como encargada de
# laboratorio y también genera residuos; Marcos Albarracín aparece en los tres.
#
# (nombre canónico, dependencia, es_encargado, es_csbqr, es_generador, alias)
PERSONAL_OFICIAL: List[Tuple[str, Optional[str], bool, bool, bool, Tuple[str, ...]]] = [
    # -- Encargados y responsables de laboratorio -----------------------------
    ("Henrry Delgado Ortega", "Ingeniería Civil", True, False, False, ("Henrry Delgado",)),
    ("Manuel Ricardo Madrid Argomedo", "Ingeniería Civil", True, False, False,
     ("Ricardo Manuel Madrid",)),
    ("Marko Lopez Bendezu", "Ingeniería Civil", True, False, False, ()),
    ("George Power Porto", "Ingeniería Civil", True, False, False, ("George Power",)),
    ("Francisco James León Trujillo", "Ingeniería Civil", True, False, False, ()),
    ("Jose Matias Leon", "Ingeniería Civil", True, False, False, ()),
    ("Darwin La Torre Esquivel", "Ingeniería Civil", True, False, False, ()),
    ("Javier Quino Favero", "Ingeniería Industrial", True, False, True, ("Javier Quino",)),
    ("Nancy Chasquibol Silva", "Ingeniería Industrial", True, False, False,
     ("Nancy Chaquibol Silva",)),
    # Firmó registros en Industrial y en Civil; se le asigna la dependencia en
    # la que aparece más veces, sin que eso le impida declarar en la otra.
    ("Juan Carlos Yacono Llanos", "Ingeniería Industrial", True, False, False,
     ("Juan Carlos Yacono",)),
    ("William Fernandez Goicochea", "Ingeniería Industrial", True, False, True, ()),
    ("Juan Carlos Goñi Delion", "Ingeniería Industrial", True, False, False,
     ("Juan Carlos Goñi Delión",)),
    ("Jorge Sanabria Villanueva", "Ingeniería Industrial", True, False, False,
     ("Jorge Sanabria",)),
    ("Wilfredo Hernández Gorritti", "Ingeniería Industrial", True, False, False,
     ("Wilfredo Hernandez Gorritti", "Wilfredo Hernandez")),
    ("Edmundo Arroyo", "Ingeniería Industrial", True, False, False, ()),
    ("Emilia Daniela Lombardi Franco", "Ingeniería Industrial", True, False, False, ()),
    ("Guillermo Davies", "Ingeniería Industrial", True, False, False, ()),
    ("Fabricio Paredes Larroca", "Ingeniería Industrial", True, False, False, ()),
    ("Patricia Larios", "Ingeniería Industrial", True, False, False, ()),
    ("Leonardo Nicolay Vinces Ramos", "Ingeniería Industrial", True, False, False, ()),
    ("Marcos Antonio Albarracin Manrique", "Ingeniería Industrial", True, True, True, ()),
    ("Jimmy Bedoya Leon", "Ingeniería Industrial", True, True, False, ()),
    ("Silvia Ponce", "Ingeniería Industrial", True, False, True, ()),
    # "Dr. Acosta" es un tratamiento, no un nombre completo: es el único del
    # histórico que no permite identificar a la persona. Se conserva tal cual
    # porque es lo que firma los registros del Departamento Médico, y queda
    # marcado para que el CSBQR lo complete.
    ("Dr. Acosta", "Departamento Médico", True, False, False, ()),

    # -- Personal del CSBQR que elabora la declaración ------------------------
    ("Christian Querevalú Borja", None, False, True, True, ()),
    ("Fiama Norabuena", None, False, True, True, ()),
    ("Irene Valdez", None, False, True, True, ()),
    ("Pamela Barreto Méndez", None, False, True, True, ("Pamela Barreto",)),
    ("Miguel Angel Leguía Martinez", None, False, True, True,
     ("Miguel Angel Leguia Martinez",)),
    ("Rafael Alarcon Rivera", None, False, True, True, ("Rafael Alarcon",)),
    ("Milagros Ariana Alvarado Apaza", None, False, True, True,
     ("Milagros Alvarado Apaza", "Milagros Alvarado")),
    ("Samuel Zegarra Poma", None, False, True, True, ("Samuel Zegarra",)),
    ("Richard Joe Osorio Mendoza", None, False, True, True,
     ("Joe Osorio Mendoza", "Richard Osorio Mendoza")),
    ("Hugo David Bedriñana Donayre", None, False, True, True, ("Hugo Bedriñana Doanyre",)),
    ("Rocio Gabriela León Cueva", None, False, True, True, ("Rocio León",)),
    ("Fernando Sandoval", None, False, True, True, ()),
    ("Mario Dayvid Carbajal Ccoyllo", None, False, True, True, ()),
    ("Alejandro Sebastian Vera Quiroz", None, False, True, True, ()),
    ("Christian García Arteaga", None, False, True, True, ()),
    ("Eber Richard Garcia Valer", None, False, True, True, ()),
    ("Juan Carlos Arca", None, False, True, True, ()),
    ("Vladimir Basilio Sulca Ñahui", None, False, True, True, ()),
    ("Gerson Ocampo", None, False, True, True, ()),
    ("Rosmelio Caldas", None, False, True, True, ()),
    ("Bryan Carhuas", None, False, True, True, ()),
    ("Michael Lujan Bastidas", None, False, True, True, ()),
    ("Ruben Torres", None, False, True, True, ()),
    ("Bary Osorio", None, False, True, True, ()),
    ("Katheryn Venturo", None, False, True, False, ()),
    # Igual que "Dr. Acosta": es un tratamiento y un apellido. Firma 13 filas
    # del histórico, así que no puede omitirse del padrón.
    ("Lic. Alvarez", None, False, True, True, ()),

    # -- Generadores que no elaboran declaraciones ---------------------------
    ("Rusbel Romero", None, False, False, True, ()),
]


def sin_acentos(texto: str) -> str:
    """Minúsculas sin acentos, para comparar sin depender de la escritura.

        >>> sin_acentos("Ácido Sulfúrico")
        'acido sulfurico'
    """
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").lower()


# Nombre interno histórico; se conserva porque lo usan las funciones de abajo.
_clave = sin_acentos


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


def clave_persona(nombre: str) -> str:
    """Clave de comparación de un nombre: sin acentos, sin dobles espacios.

    Es lo que hace equivalentes "Miguel Angel Leguía Martinez" y "Miguel Angel
    Leguia Martinez", que en el histórico son dos filas y una sola persona.
    """
    return " ".join(_clave(nombre).split())


def persona_oficial(nombre: str) -> Optional[str]:
    """Devuelve el nombre canónico de una persona del padrón, o None.

    Resuelve tanto el nombre canónico como cualquiera de sus variantes:

        >>> persona_oficial("Javier Quino")
        'Javier Quino Favero'
        >>> persona_oficial("MILAGROS ALVARADO")
        'Milagros Ariana Alvarado Apaza'
        >>> persona_oficial("Alguien que no está en el padrón") is None
        True
    """
    objetivo = clave_persona(nombre)
    if not objetivo:
        return None
    for canonico, _dep, _enc, _csbqr, _gen, alias in PERSONAL_OFICIAL:
        if objetivo == clave_persona(canonico):
            return canonico
        if any(objetivo == clave_persona(variante) for variante in alias):
            return canonico
    return None
