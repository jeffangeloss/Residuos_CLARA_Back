"""Fidelidad de la ontología y la matriz contra los archivos del Gem.

Los archivos de conocimiento del Gem (`CLARA/*.docx`) son la autoridad de
dominio, propiedad del CSBQR. Estas pruebas leen esos documentos y comprueban
que lo implementado coincide.

Su razón de ser: la divergencia anterior —24 pares peligrosos sin detectar,
dos clases de declaración invertidas, códigos Basilea truncados— apareció y
creció en silencio porque nada comparaba ambas fuentes. Si alguien edita la
ontología del código sin actualizar el Gem, o al revés, estas pruebas fallan.

Se omiten si los documentos no están disponibles, para no romper la suite en un
entorno que solo tenga el backend.
"""

import os
import re

import pytest

DIRECTORIO_GEM = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "CLARA"
)
ONTOLOGIA_DOCX = os.path.join(DIRECTORIO_GEM, "2_Gem_Conocimiento_Ontologia.md-2.docx")
MATRIZ_DOCX = os.path.join(DIRECTORIO_GEM, "3_Gem_Conocimiento_Matriz_Incompatibilidad.md.docx")

docx = pytest.importorskip("docx", reason="python-docx no está instalado")

pytestmark = pytest.mark.skipif(
    not (os.path.exists(ONTOLOGIA_DOCX) and os.path.exists(MATRIZ_DOCX)),
    reason="Los documentos de conocimiento del Gem no están disponibles",
)

# Correspondencia entre el número de categoría del Gem y su identificador interno.
IDS_CATEGORIA = {
    1: "acidos-corrosivos", 2: "bases-corrosivas", 3: "solventes-no-halogenados",
    4: "solventes-halogenados", 5: "oxidantes", 6: "metales-pesados",
    7: "envases-contaminados", 8: "aerosoles", 9: "solidos-contaminados",
    10: "biocontaminados", 11: "punzocortantes", 12: "aceites-contaminados",
    13: "raee", 14: "no-identificados", 15: "radiactivos",
}

# Etiquetas de la matriz del Gem → grupo de compatibilidad de la ontología.
GRUPOS_POR_ETIQUETA = {
    "Ácido": "ÁCIDO", "Base": "BASE", "Solv. no halog.": "INFLAMABLE",
    "Solv. halog.": "HALOGENADO", "Oxidante": "OXIDANTE", "Metal pesado": "TÓXICO-METAL",
    "Biológico": "BIOLÓGICO", "Punzocortante": "PUNZOCORTANTE", "Aceite": "ACEITE",
    "Aerosol": "PRESURIZADO", "No identificado": "AISLAR",
}
GRUPOS_POR_COLUMNA = {
    "Ácido": "ÁCIDO", "Base": "BASE", "Solv.NoHal": "INFLAMABLE", "Solv.Hal": "HALOGENADO",
    "Oxidante": "OXIDANTE", "Metal pesado": "TÓXICO-METAL", "Biológico": "BIOLÓGICO",
    "Punzocort.": "PUNZOCORTANTE", "Aceite": "ACEITE", "Aerosol": "PRESURIZADO",
    "No ident.": "AISLAR",
}

# Campos que dependen de una pregunta abierta y por eso hoy divergen a
# propósito del Gem. Ver DUDAS_CSBQR.md.
EXCEPCIONES_PENDIENTES = {
    ("envases-contaminados", "declaracion"),  # pregunta 4
    ("envases-contaminados", "basilea"),      # pregunta 4
    ("solidos-contaminados", "declaracion"),  # pregunta 4
    ("solidos-contaminados", "basilea"),      # pregunta 4
    ("radiactivos", "declaracion"),           # pregunta 5
    ("radiactivos", "basilea"),               # pregunta 5
}


def _leer_ontologia_del_gem():
    documento = docx.Document(ONTOLOGIA_DOCX)
    texto = "\n".join(p.text for p in documento.paragraphs if p.text.strip())
    categorias = {}
    for bloque in re.split(r"\n(?=\d{1,2}\.\s+[A-ZÁÉÍÓÚÑ])", texto):
        encabezado = re.match(r"(\d{1,2})\.\s+(.+)", bloque)
        if not encabezado or int(encabezado.group(1)) > 15:
            continue

        def campo(patron):
            hallazgo = re.search(patron, bloque)
            return hallazgo.group(1).strip() if hallazgo else None

        categorias[int(encabezado.group(1))] = {
            "caracteristica": campo(r"Característica:\s*(.+?)\s*·"),
            "grupo": campo(r"Grupo:\s*(.+)"),
            "declaracion": campo(r"Declaración:\s*(.+?)\s*·"),
            "basilea": campo(r"Basilea:\s*(.+)"),
            "noAlmacenarConTexto": campo(r"NO almacenar con:\s*(.+)"),
        }
    return categorias


def _leer_matriz_del_gem():
    documento = docx.Document(MATRIZ_DOCX)
    filas = [[celda.text.strip() for celda in fila.cells] for fila in documento.tables[1].rows]
    columnas = filas[0][1:]
    celdas = {}
    for fila in filas[1:]:
        grupo_fila = GRUPOS_POR_ETIQUETA.get(fila[0])
        if not grupo_fila:
            continue
        for indice, valor in enumerate(fila[1:1 + len(columnas)]):
            grupo_columna = GRUPOS_POR_COLUMNA.get(columnas[indice])
            if grupo_columna and valor:
                celdas[tuple(sorted((grupo_fila, grupo_columna)))] = valor
    return celdas


# --------------------------------------------------------------------------
# Ontología
# --------------------------------------------------------------------------

def test_la_ontologia_del_codigo_tiene_las_quince_categorias_del_gem():
    from core.classifier import ONTOLOGIA

    assert len(_leer_ontologia_del_gem()) == 15
    assert len(ONTOLOGIA) == 15


@pytest.mark.parametrize(
    "campo", ["caracteristica", "grupo", "declaracion", "basilea", "noAlmacenarConTexto"]
)
def test_cada_campo_de_la_ontologia_coincide_con_el_gem(campo):
    from core.classifier import ONTOLOGIA

    gem = _leer_ontologia_del_gem()
    diferencias = []
    for numero, datos_gem in gem.items():
        identificador = IDS_CATEGORIA[numero]
        if (identificador, campo) in EXCEPCIONES_PENDIENTES:
            continue
        esperado = datos_gem[campo]
        if esperado is None:
            continue  # El Gem no fija valor para ese campo en esa categoría.
        obtenido = ONTOLOGIA[identificador][campo]
        if obtenido != esperado:
            diferencias.append(f"{identificador}.{campo}: código={obtenido!r} gem={esperado!r}")

    assert not diferencias, "Divergencias con el Gem:\n  " + "\n  ".join(diferencias)


def test_las_excepciones_pendientes_siguen_documentadas():
    """Si una pregunta se resuelve, hay que quitar su excepción de esta lista."""
    import pathlib

    dudas = pathlib.Path(DIRECTORIO_GEM).parent / "DUDAS_CSBQR.md"
    assert dudas.exists(), "Falta DUDAS_CSBQR.md que justifica las excepciones"
    contenido = dudas.read_text(encoding="utf-8")
    for identificador, campo in EXCEPCIONES_PENDIENTES:
        assert identificador in contenido, (
            f"La excepción {identificador}.{campo} no está justificada en DUDAS_CSBQR.md"
        )


# --------------------------------------------------------------------------
# Matriz de incompatibilidad
# --------------------------------------------------------------------------

def test_la_matriz_del_codigo_reproduce_la_del_gem():
    from core.classifier import MATRIZ_CSBQR, VEREDICTOS_MATRIZ

    equivalencia = {"N": "NUNCA", "S": "SEGREGAR", "○": "COMPATIBLE"}
    assert set(VEREDICTOS_MATRIZ.values()) == set(equivalencia.values())

    diferencias = []
    for par, simbolo in _leer_matriz_del_gem().items():
        esperado = equivalencia[simbolo]
        obtenido = MATRIZ_CSBQR[par][0]
        if obtenido != esperado:
            diferencias.append(f"{par[0]}+{par[1]}: código={obtenido} gem={esperado}")

    assert not diferencias, "Celdas que no coinciden con el Gem:\n  " + "\n  ".join(diferencias)


def test_la_matriz_cubre_todos_los_pares_del_gem():
    from core.classifier import MATRIZ_CSBQR

    del_gem = set(_leer_matriz_del_gem())
    assert del_gem == set(MATRIZ_CSBQR), (
        f"Faltan en el código: {del_gem - set(MATRIZ_CSBQR)} · "
        f"Sobran en el código: {set(MATRIZ_CSBQR) - del_gem}"
    )


def test_la_matriz_sembrada_en_la_base_coincide_con_el_gem(db):
    """La comprobación que de verdad importa: lo que evalúa el acopio."""
    from core.repositorio import matriz_incompatibilidad

    equivalencia = {"N": "NUNCA", "S": "SEGREGAR", "○": "COMPATIBLE"}
    en_base = matriz_incompatibilidad(db)

    diferencias = []
    for par, simbolo in _leer_matriz_del_gem().items():
        esperado = equivalencia[simbolo]
        obtenido = en_base.get(par, (None, None))[0]
        if obtenido != esperado:
            diferencias.append(f"{par[0]}+{par[1]}: base={obtenido} gem={esperado}")

    assert not diferencias, "La base no refleja la matriz del Gem:\n  " + "\n  ".join(diferencias)


def test_todos_los_grupos_de_la_ontologia_resuelven_un_veredicto(db):
    """Ningún grupo puede quedar sin respuesta en el punto de acopio."""
    from core.classifier import ONTOLOGIA
    from core.repositorio import evaluar_compatibilidad

    grupos = sorted({c["grupo"] for c in ONTOLOGIA.values()})
    for grupo_a in grupos:
        for grupo_b in grupos:
            veredicto = evaluar_compatibilidad(db, [grupo_a, grupo_b])["veredicto"]
            assert veredicto in {"NUNCA", "SEGREGAR", "COMPATIBLE"}
