"""
Motor Determinista de Clasificación y Matriz de Incompatibilidad (CORE V3)
Universidad de Lima - CSBQR
"""

from typing import List, Dict, Tuple
from core.models import EntradaResiduoRequest, ResultadoClasificacion

# Ontología Canónica ULima (15 Categorías)
ONTOLOGIA = {
    "acidos-corrosivos": {
        "n": 1, "nombre": "Ácidos corrosivos", "caracteristica": "Corrosivo", "grupo": "ÁCIDO",
        "noAlmacenarCon": ["bases", "metales", "oxidantes", "cianuros", "sulfuros"],
        "envase": "bidón o frasco de plástico rígido resistente a ácidos con contención secundaria",
        "declaracion": "Sustancias corrosivas", "basilea": "H8"
    },
    "bases-corrosivas": {
        "n": 2, "nombre": "Bases corrosivas", "caracteristica": "Corrosivo", "grupo": "BASE",
        "noAlmacenarCon": ["ácidos", "metales anfóteros (Al, Zn)", "oxidantes"],
        "envase": "bidón o frasco de plástico rígido resistente a químicos con contención secundaria",
        "declaracion": "Sustancias corrosivas", "basilea": "H8"
    },
    "solventes-no-halogenados": {
        "n": 3, "nombre": "Solventes no halogenados", "caracteristica": "Inflamable", "grupo": "INFLAMABLE",
        "noAlmacenarCon": ["oxidantes", "ácidos/bases fuertes", "fuentes de ignición"],
        "envase": "frasco de vidrio ámbar o contenedor metálico con toma a tierra",
        "declaracion": "Líquidos Inflamables", "basilea": "H3"
    },
    "solventes-halogenados": {
        "n": 4, "nombre": "Solventes halogenados", "caracteristica": "Tóxico", "grupo": "HALOGENADO",
        "noAlmacenarCon": ["oxidantes", "metales reactivos", "solventes no halogenados"],
        "envase": "frasco de vidrio ámbar resistente con etiqueta especial de halogenados",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H11"
    },
    "oxidantes": {
        "n": 5, "nombre": "Sustancias oxidantes", "caracteristica": "Oxidante", "grupo": "OXIDANTE",
        "noAlmacenarCon": ["inflamables", "orgánicos", "reductores", "ácidos concentrados"],
        "envase": "frasco de vidrio o plástico compatible con contención secundaria",
        "declaracion": "Sustancias oxidantes y peróxidos orgánicos", "basilea": "H5.1"
    },
    "metales-pesados": {
        "n": 6, "nombre": "Residuos con metales pesados", "caracteristica": "Tóxico", "grupo": "TÓXICO-METAL",
        "noAlmacenarCon": ["ácidos concentrados", "cianuros"],
        "envase": "frasco hermético con contención secundaria y rotulado del metal",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H11 / H12"
    },
    "biocontaminados": {
        "n": 10, "nombre": "Residuos biocontaminados", "caracteristica": "Infeccioso", "grupo": "BIOLÓGICO",
        "noAlmacenarCon": ["residuos químicos", "reactivos corrosivos", "punzocortantes fuera de caja"],
        "envase": "bolsa roja de bioseguridad autoclavable",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H6.2"
    },
    "punzocortantes": {
        "n": 11, "nombre": "Objetos punzocortantes", "caracteristica": "Infeccioso", "grupo": "PUNZOCORTANTE",
        "noAlmacenarCon": ["bolsas suaves", "líquidos libres"],
        "envase": "caja rígida amarilla de polipropileno resistente a punciones",
        "declaracion": "Sustancias tóxicas e infecciosas", "basilea": "H6.2"
    },
    "no-identificados": {
        "n": 14, "nombre": "No identificado / En evaluación", "caracteristica": "En evaluación", "grupo": "AISLAR",
        "noAlmacenarCon": ["CUALQUIER OTRO RESIDUO"],
        "envase": "recipiente hermético con contención secundaria transparente y etiqueta de advertencia",
        "declaracion": "En evaluación / consultar CSBQR", "basilea": "A1180"
    }
}

# Pares prohibidos (Matriz 11x11 CSBQR)
PARES_PROHIBIDOS = [
    ("ÁCIDO", "BASE", "Neutralización violenta, calor y salpicaduras"),
    ("ÁCIDO", "CIANURO", "Libera gas cianhídrico (HCN), letal"),
    ("ÁCIDO", "SULFURO", "Libera sulfuro de hidrógeno (H2S), tóxico"),
    ("ÁCIDO", "TÓXICO-METAL", "Moviliza metales pesados y genera gas"),
    ("OXIDANTE", "INFLAMABLE", "Reacción exotérmica violenta o ignición"),
]

def clasificar_residuo(req: EntradaResiduoRequest) -> ResultadoClasificacion:
    # 1. Regla Canónica de Unidad: Peso neto en GRAMOS
    peso_neto_g = max(0.0, req.peso_bruto_g - req.tara_g)
    
    # 2. Conversión a KG en UN SOLO LUGAR (Principio CORE V3)
    peso_neto_kg = round(peso_neto_g / 1000.0, 4)

    # 3. Determinación de Categoría Interna
    if req.desconocido:
        cat_id = "no-identificados"
    elif req.es_punzocortante:
        cat_id = "punzocortantes"
    elif req.es_biologico:
        cat_id = "biocontaminados"
    else:
        # Inferencia por insumos ingresados
        texto_insumos = " ".join(req.insumos).lower()
        if any(m in texto_insumos for m in ["cobre", "hierro", "plomo", "zinc", "mercurio"]):
            cat_id = "metales-pesados"
        elif any(a in texto_insumos for a in ["ácido", "sulfúrico", "clorhídrico", "nítrico"]):
            cat_id = "acidos-corrosivos"
        elif any(b in texto_insumos for b in ["hidróxido", "sodio", "potasio", "amonio"]):
            cat_id = "bases-corrosivas"
        elif any(s in texto_insumos for s in ["acetona", "etanol", "metanol", "hexano"]):
            cat_id = "solventes-no-halogenados"
        else:
            cat_id = "metales-pesados" # fallback seguro con alta peligrosidad

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

    # 5. Generación de Nombre Normalizado
    nombre_norm = f"Solución residual de {', '.join(req.insumos)}" if req.insumos else req.descripcion

    return ResultadoClasificacion(
        id_residuo=f"RES-{int(peso_neto_g)}-001",
        nombre_normalizado=nombre_norm,
        categoria_id=cat_id,
        categoria_nombre=cat_info["nombre"],
        caracteristica_principal=cat_info["caracteristica"],
        clase_declaracion_sunat=cat_info["declaracion"],
        clase_basilea=cat_info["basilea"],
        grupo_compatibilidad=cat_info["grupo"],
        no_mezclar_con=cat_info["noAlmacenarCon"],
        envase_recomendado=cat_info["envase"],
        peso_neto_g=peso_neto_g,
        peso_neto_kg=peso_neto_kg,
        confianza="Alto" if not req.desconocido else "Bajo",
        observaciones=["Llenar como máximo al 75%", "No verter al desagüe"],
        pictogramas_ghs=pictogramas,
        escalar_csbqr=req.desconocido,
        narrativa=f"Residuo catalogado como {cat_info['nombre']}. Requiere almacenamiento segregado."
    )
