"""
Motor Determinista de Clasificación y Matriz de Incompatibilidad (CORE V3)
Universidad de Lima - CSBQR
"""

from typing import List, Dict, Tuple
from uuid import uuid4
from core.models import (
    EntradaResiduoRequest, EstadoFisico, ModoMedicion, ResultadoClasificacion, Unidad,
)

# Ontología Canónica ULima (15 Categorías)
# `noAlmacenarConTexto` reproduce literalmente la línea "NO almacenar con:" del
# archivo de conocimiento del Gem, que es la autoridad de dominio. Es el texto
# que se imprime en la etiqueta y el que verifica la prueba de fidelidad.
# `noAlmacenarCon` es el mismo contenido troceado para mostrarlo como etiquetas
# en la interfaz.
#
# Los campos marcados con "PENDIENTE CSBQR" conservan el valor anterior a
# propósito: dependen de una pregunta abierta. Ver DUDAS_CSBQR.md.
ONTOLOGIA = {
    "acidos-corrosivos": {
        "n": 1, "nombre": "Ácidos corrosivos", "caracteristica": "Corrosivo", "caracteristicaDeclaracion": "Corrosividad", "grupo": "ÁCIDO",
        "noAlmacenarCon": ["bases", "metales", "oxidantes", "cianuros", "sulfuros"],
        "noAlmacenarConTexto": "bases, metales, oxidantes, cianuros y sulfuros",
        "envase": "bidón o frasco de plástico rígido resistente a ácidos con contención secundaria",
        "declaracion": "Sustancias corrosivas", "basilea": "H8"
    },
    "bases-corrosivas": {
        "n": 2, "nombre": "Bases corrosivas", "caracteristica": "Corrosivo", "caracteristicaDeclaracion": "Corrosividad", "grupo": "BASE",
        "noAlmacenarCon": ["ácidos", "metales anfóteros (Al, Zn)", "oxidantes"],
        "noAlmacenarConTexto": "ácidos, metales anfóteros (Al, Zn), oxidantes",
        "envase": "bidón o frasco de plástico rígido resistente a químicos con contención secundaria",
        "declaracion": "Sustancias corrosivas", "basilea": "H8"
    },
    "solventes-no-halogenados": {
        "n": 3, "nombre": "Solventes no halogenados", "caracteristica": "Inflamable", "caracteristicaDeclaracion": "Inflamabilidad", "grupo": "INFLAMABLE",
        "noAlmacenarCon": ["oxidantes", "ácidos/bases fuertes", "fuentes de ignición"],
        "noAlmacenarConTexto": "oxidantes, ácidos/bases fuertes, fuentes de ignición",
        "envase": "frasco de vidrio ámbar o contenedor metálico con toma a tierra",
        "declaracion": "Líquidos Inflamables", "basilea": "H3"
    },
    "solventes-halogenados": {
        "n": 4, "nombre": "Solventes halogenados", "caracteristica": "Tóxico", "caracteristicaDeclaracion": "Toxicidad (+ inflamabilidad en algunos)", "grupo": "HALOGENADO",
        "noAlmacenarCon": ["bases", "metales reactivos (Na, Al)", "oxidantes", "solventes no halogenados"],
        "noAlmacenarConTexto": "bases y metales reactivos (Na, Al), oxidantes, y solventes no halogenados",
        "envase": "frasco de vidrio ámbar resistente con etiqueta especial de halogenados",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H6.1 / H11"
    },
    "oxidantes": {
        "n": 5, "nombre": "Sustancias oxidantes", "caracteristica": "Oxidante", "caracteristicaDeclaracion": "Reactividad (+ explosividad en peróxidos)", "grupo": "OXIDANTE",
        "noAlmacenarCon": ["inflamables", "orgánicos", "reductores", "ácidos"],
        "noAlmacenarConTexto": "inflamables, orgánicos, reductores, ácidos",
        "envase": "frasco de vidrio o plástico compatible con contención secundaria",
        "declaracion": "Sustancias oxidantes y peróxidos orgánicos", "basilea": "H5.1 / H5.2"
    },
    "metales-pesados": {
        "n": 6, "nombre": "Residuos con metales pesados", "caracteristica": "Tóxico / Ecotóxico", "caracteristicaDeclaracion": "Toxicidad (+ ecotoxicidad)", "grupo": "TÓXICO-METAL",
        "noAlmacenarCon": ["ácidos concentrados", "sulfuros/cianuros", "segregar de otros metales"],
        "noAlmacenarConTexto": "ácidos concentrados, sulfuros/cianuros; segregar de otros metales",
        "envase": "frasco hermético con contención secundaria y rotulado del metal",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H11 / H12 (+ código A específico)"
    },
    "envases-contaminados": {
        "n": 7, "nombre": "Envases vacíos contaminados", "caracteristica": "heredada del contaminante", "caracteristicaDeclaracion": "Heredada del contaminante", "grupo": "SEGÚN CONTAMINANTE",
        "noAlmacenarCon": ["según el contaminante residual"],
        "noAlmacenarConTexto": "según el contaminante residual",
        "envase": "bolsa roja/amarilla de polietileno de alta densidad o caja etiquetada",
        # PENDIENTE CSBQR (pregunta 4): el Gem dice "según el contaminante"; se
        # mantiene el valor por defecto que el propio Gem indica para el caso
        # desconocido, hasta decidir si la app debe preguntar el contaminante.
        "declaracion": "Sustancias y objetos peligrosos diversos", "basilea": "H13"
    },
    "aerosoles": {
        "n": 8, "nombre": "Aerosoles y presurizados", "caracteristica": "Inflamable / Reactivo (presión)", "caracteristicaDeclaracion": "Reactividad / inflamabilidad (por presión)", "grupo": "PRESURIZADO",
        "noAlmacenarCon": ["calor y fuentes de ignición", "no perforar ni compactar"],
        "noAlmacenarConTexto": "calor y fuentes de ignición; no perforar ni compactar",
        "envase": "caja o contenedor rígido ventilado",
        "declaracion": "Sustancias y objetos peligrosos diversos", "basilea": "H1 / H3"
    },
    "solidos-contaminados": {
        "n": 9, "nombre": "Sólidos contaminados", "caracteristica": "heredada del contaminante", "caracteristicaDeclaracion": "Heredada del contaminante", "grupo": "SEGÚN CONTAMINANTE",
        "noAlmacenarCon": ["según el contaminante"],
        "noAlmacenarConTexto": "según el contaminante",
        "envase": "bolsa plástica gruesa dentro de tambor de polietileno",
        # PENDIENTE CSBQR (pregunta 4): mismo caso que envases contaminados.
        "declaracion": "Sustancias y objetos peligrosos diversos", "basilea": "H11"
    },
    "biocontaminados": {
        "n": 10, "nombre": "Residuos biocontaminados", "caracteristica": "Infeccioso", "caracteristicaDeclaracion": "Patogenicidad", "grupo": "BIOLÓGICO",
        "noAlmacenarCon": ["residuos químicos"],
        "noAlmacenarConTexto": "residuos químicos",
        "envase": "bolsa roja de bioseguridad autoclavable",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H6.2"
    },
    "punzocortantes": {
        "n": 11, "nombre": "Objetos punzocortantes", "caracteristica": "Infeccioso / según contaminante", "caracteristicaDeclaracion": "Patogenicidad (o la del contaminante)", "grupo": "PUNZOCORTANTE",
        "noAlmacenarCon": ["no reabrir", "no mezclar con otros residuos"],
        "noAlmacenarConTexto": "no reabrir; no mezclar con otros residuos",
        "envase": "caja rígida amarilla de polipropileno resistente a punciones",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H6.2"
    },
    "aceites-contaminados": {
        "n": 12, "nombre": "Aceites usados y lubricantes", "caracteristica": "Inflamable / Tóxico", "caracteristicaDeclaracion": "Inflamabilidad (+ toxicidad)", "grupo": "ACEITE",
        "noAlmacenarCon": ["solventes", "oxidantes", "agua", "fuentes de calor"],
        "noAlmacenarConTexto": "solventes, oxidantes, agua, fuentes de calor",
        "envase": "bidón plástico o metálico hermético",
        "declaracion": "Líquidos Inflamables", "basilea": "H3 / H11"
    },
    "raee": {
        "n": 13, "nombre": "Residuos de aparatos eléctricos (RAEE)", "caracteristica": "Tóxico (metales pesados)", "caracteristicaDeclaracion": "Toxicidad", "grupo": "RAEE",
        "noAlmacenarCon": ["no desarmar", "segregar de residuos húmedos"],
        "noAlmacenarConTexto": "no desarmar; segregar de residuos húmedos",
        "envase": "caja reforzada o palet acordonado",
        "declaracion": "Sustancias y objetos peligrosos diversos", "basilea": "H11 / H12"
    },
    "no-identificados": {
        "n": 14, "nombre": "No identificado / En evaluación", "caracteristica": "En evaluación — tratar como MÁXIMO peligro", "caracteristicaDeclaracion": "En evaluación", "grupo": "AISLAR",
        "noAlmacenarCon": ["TODO — no mezclar con nada", "aislar"],
        "noAlmacenarConTexto": "TODO — no mezclar con nada; aislar",
        "envase": "recipiente hermético con contención secundaria transparente y etiqueta de advertencia",
        # El valor anterior era "A1180", que es el código Basilea de residuos de
        # aparatos eléctricos y electrónicos: correspondía a RAEE, no a un
        # residuo sin identificar.
        "declaracion": "En evaluación / consultar CSBQR", "basilea": "por determinar"
    },
    "radiactivos": {
        "n": 15, "nombre": "Residuos radioactivos", "caracteristica": "Radiactivo", "caracteristicaDeclaracion": "Radioactividad", "grupo": "RADIACTIVO",
        "noAlmacenarCon": ["CUALQUIER OTRO RESIDUO"],
        "noAlmacenarConTexto": "CUALQUIER OTRO RESIDUO",
        "envase": "contenedor blindado según isótopo",
        # PENDIENTE CSBQR (pregunta 5): el Gem no asigna clase de declaración ni
        # código Basilea porque van por régimen IPEN separado.
        "declaracion": "En evaluación / consultar CSBQR", "basilea": "IPEN"
    }
}

# Nivel de confianza según cómo se determinó la categoría.
#
# La RF-04 exige mostrar Alto, Medio o Bajo, pero el motor solo emitía Alto y
# Bajo: una categoría deducida por palabras clave se presentaba con la misma
# certeza que una declarada explícitamente por el usuario.
#
# PENDIENTE DE VALIDACIÓN: el corte entre los tres niveles es criterio de
# dominio y debe confirmarlo el responsable técnico/ambiental de ULima.
CONFIANZA_POR_ORIGEN = {
    "declarado": "Alto",   # El usuario marcó un indicador explícito.
    "inferido": "Medio",   # Deducida por palabras clave en los insumos.
    "sin_datos": "Bajo",   # Sin elementos para determinar la categoría.
}

# ---------------------------------------------------------------------------
# Matriz de Incompatibilidad y Segregación CSBQR (11×11)
#
# Transcrita del archivo de conocimiento del Gem
# "3_Gem_Conocimiento_Matriz_Incompatibilidad.md", que es la autoridad de
# dominio. Antes aquí solo había 5 pares prohibidos: la app respondía SEGREGAR
# —permisivo— en 24 combinaciones que el CSBQR marca como NUNCA.
#
# Leyenda: N = nunca juntos · S = segregar · O = compatible
#
# La diagonal es O salvo en AISLAR: dos residuos sin identificar tampoco pueden
# juntarse entre sí, porque se desconoce si son compatibles.
# ---------------------------------------------------------------------------

GRUPOS_MATRIZ = [
    "ÁCIDO", "BASE", "INFLAMABLE", "HALOGENADO", "OXIDANTE", "TÓXICO-METAL",
    "BIOLÓGICO", "PUNZOCORTANTE", "ACEITE", "PRESURIZADO", "AISLAR",
]

# Filas en el mismo orden que GRUPOS_MATRIZ.
_FILAS_MATRIZ = """
O N S S N N N S S S N
N O S N N S N S S S N
S S O S N S N S S S N
S N S O N S N S S S N
N N N N O S N S N N N
N S S S S O N S S S N
N N N N N N O S N N N
S S S S S S S O S S N
S S S S N S N S O S N
S S S S N S N S S O N
N N N N N N N N N N N
"""

VEREDICTOS_MATRIZ = {"N": "NUNCA", "S": "SEGREGAR", "O": "COMPATIBLE"}

# Explicaciones de riesgo tomadas de la tabla "Pares que NUNCA deben juntarse"
# del mismo archivo del Gem.
_RAZONES_ESPECIFICAS = {
    ("BASE", "ÁCIDO"): "Neutralización violenta, calor, salpicaduras",
    ("TÓXICO-METAL", "ÁCIDO"): "Genera hidrógeno (inflamable) y moviliza metales",
    ("INFLAMABLE", "OXIDANTE"): "Fuego o explosión",
    ("HALOGENADO", "OXIDANTE"): "Fuego o explosión",
    ("ACEITE", "OXIDANTE"): "Fuego o explosión",
    ("OXIDANTE", "PRESURIZADO"): "Estallido y proyección por calor o ignición",
    ("BASE", "HALOGENADO"): "Los solventes halogenados reaccionan con bases fuertes",
    ("BASE", "OXIDANTE"): "Reacción exotérmica violenta",
    ("OXIDANTE", "ÁCIDO"): "Reacción violenta; un ácido oxidante puede inflamar materia orgánica",
}

# Cuando el par no tiene una explicación específica, se usa la del grupo que
# gobierna el riesgo, en este orden de prioridad.
_RAZON_POR_GRUPO = [
    ("AISLAR", "Riesgo desconocido: aislar siempre hasta que el CSBQR lo identifique"),
    ("BIOLÓGICO", "Rompe la ruta de tratamiento; riesgo de reacción"),
    ("OXIDANTE", "Fuego o explosión"),
]


def _razon_incompatibilidad(grupo_a: str, grupo_b: str) -> str:
    par = tuple(sorted((grupo_a, grupo_b)))
    if par in _RAZONES_ESPECIFICAS:
        return _RAZONES_ESPECIFICAS[par]
    for grupo, razon in _RAZON_POR_GRUPO:
        if grupo in par:
            return razon
    return "Incompatibilidad declarada en la matriz CSBQR"


def _construir_matriz() -> Dict[Tuple[str, str], Tuple[str, str]]:
    """Convierte la rejilla en pares canónicos {(A,B): (veredicto, razón)}."""
    filas = [f.split() for f in _FILAS_MATRIZ.strip().splitlines()]
    if len(filas) != len(GRUPOS_MATRIZ) or any(len(f) != len(GRUPOS_MATRIZ) for f in filas):
        raise ValueError("La matriz CSBQR no es cuadrada respecto a GRUPOS_MATRIZ")

    matriz = {}
    for i, grupo_a in enumerate(GRUPOS_MATRIZ):
        for j, grupo_b in enumerate(GRUPOS_MATRIZ):
            if filas[i][j] != filas[j][i]:
                raise ValueError(f"La matriz CSBQR no es simétrica en {grupo_a}/{grupo_b}")
            veredicto = VEREDICTOS_MATRIZ[filas[i][j]]
            par = tuple(sorted((grupo_a, grupo_b)))
            razon = (
                _razon_incompatibilidad(grupo_a, grupo_b) if veredicto == "NUNCA"
                else "Grupos químicos distintos: separar en bandejas o contenciones diferentes"
                if veredicto == "SEGREGAR"
                else "Mismo grupo de compatibilidad"
            )
            matriz[par] = (veredicto, razon)
    return matriz


MATRIZ_CSBQR = _construir_matriz()

# Pares que además figuran en la tabla de prosa del Gem pero cuyos grupos no
# existen todavía en la ontología: hoy no se pueden disparar. Se conservan para
# no perder el criterio del CSBQR mientras se resuelve si cianuros y sulfuros
# deben ser grupos propios (ver DUDAS_CSBQR.md, pregunta 2).
PARES_SIN_GRUPO_ASIGNADO = [
    ("ÁCIDO", "CIANURO", "Libera gas cianhídrico (HCN), letal"),
    ("ÁCIDO", "SULFURO", "Libera sulfuro de hidrógeno (H₂S), tóxico"),
]

def clasificar_residuo(req: EntradaResiduoRequest) -> ResultadoClasificacion:
    # 1. Cantidad declarada, según el modo de medición.
    #
    # Con balanza: peso neto = bruto − tara, y la cantidad se declara en Kg.
    # La conversión a kilogramos ocurre en este único lugar.
    #
    # Sin balanza: la cantidad y su unidad son las que indicó quien declara.
    if req.modo_medicion is ModoMedicion.PESAJE:
        peso_neto_g = max(0.0, req.peso_bruto_g - req.tara_g)
        cantidad = round(peso_neto_g / 1000.0, 4)
        unidad = Unidad.KG
    else:
        peso_neto_g = None
        cantidad = req.cantidad
        unidad = req.unidad

    # 3. Determinación de Categoría Interna
    #
    # `origen_categoria` distingue cómo se llegó a la categoría, porque de eso
    # depende cuánta confianza merece el resultado:
    #   declarado - el usuario marcó un indicador explícito
    #   inferido  - se dedujo por palabras clave en los insumos, que es una
    #               heurística y puede errar
    #   sin_datos - no hay elementos para determinar la categoría
    if req.desconocido:
        cat_id = "no-identificados"
        origen_categoria = "sin_datos"
    elif req.es_punzocortante:
        cat_id = "punzocortantes"
        origen_categoria = "declarado"
    elif req.es_biologico:
        cat_id = "biocontaminados"
        origen_categoria = "declarado"
    elif req.es_aerosol:
        cat_id = "aerosoles"
        origen_categoria = "declarado"
    elif req.es_envase_vacio:
        cat_id = "envases-contaminados"
        origen_categoria = "declarado"
    else:
        origen_categoria = "inferido"
        # Inferencia por insumos ingresados
        texto_insumos = " ".join(req.insumos).lower()
        if any(r in texto_insumos for r in ["radioactivo", "radiactivo", "isótopo", "isotopo"]):
            cat_id = "radiactivos"
        elif any(e in texto_insumos for e in ["raee", "computadora", "monitor", "electrónico", "electronico", "batería", "bateria"]):
            cat_id = "raee"
        elif any(a in texto_insumos for a in ["aceite", "lubricante"]):
            cat_id = "aceites-contaminados"
        elif any(h in texto_insumos for h in ["cloroformo", "diclorometano", "cloruro de metileno", "halogenado"]):
            cat_id = "solventes-halogenados"
        elif any(o in texto_insumos for o in ["permanganato", "peróxido", "peroxido", "nitrato", "hipoclorito"]):
            cat_id = "oxidantes"
        elif any(m in texto_insumos for m in ["cobre", "hierro", "plomo", "zinc", "mercurio"]):
            cat_id = "metales-pesados"
        elif any(a in texto_insumos for a in ["ácido", "sulfúrico", "clorhídrico", "nítrico"]):
            cat_id = "acidos-corrosivos"
        elif any(b in texto_insumos for b in ["hidróxido", "sodio", "potasio", "amonio"]):
            cat_id = "bases-corrosivas"
        elif any(s in texto_insumos for s in ["acetona", "etanol", "metanol", "hexano"]):
            cat_id = "solventes-no-halogenados"
        else:
            cat_id = "no-identificados"
            origen_categoria = "sin_datos"

    cat_info = ONTOLOGIA.get(cat_id, ONTOLOGIA["no-identificados"])

    # 4. Asignación de Pictogramas GHS
    pictogramas = []
    if cat_id in ["acidos-corrosivos", "bases-corrosivas"] or (req.ph and (req.ph <= 2.0 or req.ph >= 11.5)):
        pictogramas.append("corrosion")
    if cat_id == "metales-pesados":
        pictogramas.append("calavera")
        pictogramas.append("medio-ambiente")
    if cat_id == "solventes-no-halogenados":
        pictogramas.append("llama")
    if cat_id == "solventes-halogenados":
        pictogramas.extend(["peligro-salud", "medio-ambiente"])
    if cat_id == "aerosoles":
        pictogramas.extend(["llama", "cilindro-gas"])
    if cat_id == "oxidantes":
        pictogramas.append("llama-sobre-circulo")
    if cat_id == "radiactivos":
        pictogramas.append("peligro-salud")

    # 5. Observaciones de manejo
    observaciones = ["Llenar como máximo al 75%", "No verter al desagüe"]
    if origen_categoria == "inferido":
        observaciones.append(
            "Categoría deducida de los insumos declarados: verifique antes de rotular"
        )
    if req.modo_medicion is ModoMedicion.PESAJE and req.tara_g > req.peso_bruto_g:
        # El peso neto queda en cero por la regla de la RF-02, pero eso casi
        # siempre indica que los campos se llenaron al revés.
        observaciones.append(
            "La tara supera al peso bruto: revise la medición antes de declarar"
        )

    # Los dos desajustes de unidad que el curador del Excel histórico anotó 195
    # veces. No se bloquea la declaración: se deja constancia.
    if req.modo_medicion is ModoMedicion.DECLARADA and unidad is Unidad.KG:
        observaciones.append(
            "Masa declarada sin pesaje: el kilogramo debe salir de una balanza"
        )
    if unidad is Unidad.L and req.estado_fisico is EstadoFisico.SOLIDO:
        observaciones.append(
            "Sólido declarado en litros: confirme la unidad o pese el envase"
        )

    # 6. Generación de Nombre Normalizado
    # Se recorta a la longitud de la columna `nombre_normalizado` para que una
    # lista larga de insumos no impida persistir la declaración.
    nombre_norm = f"Solución residual de {', '.join(req.insumos)}" if req.insumos else req.descripcion
    if len(nombre_norm) > 300:
        nombre_norm = nombre_norm[:297] + "..."

    return ResultadoClasificacion(
        id_residuo=f"RES-{uuid4().hex[:12].upper()}",
        nombre_normalizado=nombre_norm,
        categoria_id=cat_id,
        categoria_nombre=cat_info["nombre"],
        caracteristica_principal=cat_info["caracteristica"],
        clase_declaracion_sunat=cat_info["declaracion"],
        clase_basilea=cat_info["basilea"],
        grupo_compatibilidad=cat_info["grupo"],
        no_mezclar_con=cat_info["noAlmacenarCon"],
        envase_recomendado=cat_info["envase"],
        cantidad=cantidad,
        unidad=unidad,
        modo_medicion=req.modo_medicion,
        peso_bruto_g=req.peso_bruto_g,
        tara_g=req.tara_g if req.modo_medicion is ModoMedicion.PESAJE else None,
        peso_neto_g=peso_neto_g,
        confianza=CONFIANZA_POR_ORIGEN[origen_categoria],
        observaciones=observaciones,
        pictogramas_ghs=pictogramas,
        escalar_csbqr=req.desconocido or cat_id in {"no-identificados", "radiactivos"},
        narrativa=f"Residuo catalogado como {cat_info['nombre']}. Requiere almacenamiento segregado."
    )
