"""
Módulo de Migración y Validación de la Base Histórica DB_DeclaraciónResiduosPeligrosos.xlsx
Analiza los 102 registros cabecera y 856 residuos declarados.
"""

import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, List, Any
from core.classifier import clasificar_residuo
from core.models import EntradaResiduoRequest

def parsear_base_historica(excel_path: str) -> Dict[str, Any]:
    with zipfile.ZipFile(excel_path) as z:
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            tree = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for elem in tree.iter():
                if elem.tag.endswith('t') and elem.text:
                    shared_strings.append(elem.text)

        def get_sheet_rows(sheet_idx):
            sheet_path = f'xl/worksheets/sheet{sheet_idx}.xml'
            rows = []
            if sheet_path in z.namelist():
                stree = ET.fromstring(z.read(sheet_path))
                for row in stree.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                    row_vals = []
                    for cell in row.iter('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c'):
                        t = cell.attrib.get('t')
                        v = cell.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                        val = v.text if v is not None else ''
                        if t == 's' and val.isdigit() and int(val) < len(shared_strings):
                            val = shared_strings[int(val)]
                        row_vals.append(str(val))
                    if row_vals:
                        rows.append(row_vals)
            return rows

        reg_rows = get_sheet_rows(1)
        res_rows = get_sheet_rows(2)

    # 1. Mapa de Registros Cabecera (Id_Registro -> Data)
    registros_map = {}
    for r in reg_rows[1:]:
        if r and len(r) > 0:
            id_reg = r[0]
            registros_map[id_reg] = {
                "id_registro": id_reg,
                "marca_temporal": r[1] if len(r) > 1 else "",
                "email": r[2] if len(r) > 2 else "",
                "dependencia": r[3] if len(r) > 3 else "Ingeniería Industrial",
                "laboratorio": r[4] if len(r) > 4 else "Química General",
                "responsable": r[5] if len(r) > 5 else "No especificado",
                "elaborado_por": r[6] if len(r) > 6 else ""
            }

    # 2. Procesar 856 Residuos
    residuos_procesados = []
    inconsistencias = {
        "caracteristicas_vacias": 0,
        "envases_vacios": 0,
        "registros_en_litros": 0,
        "registros_en_kg": 0
    }

    for r in res_rows[1:]:
        if not r or len(r) < 10:
            continue
        
        id_res = r[0]
        id_reg = r[3] if len(r) > 3 else ""
        cabecera = registros_map.get(id_reg, {
            "dependencia": "Ingeniería Industrial",
            "laboratorio": "Química General",
            "responsable": "Responsable Lab"
        })

        nombre_residuo = r[9] if len(r) > 9 else "Residuo sin nombre"
        caracteristica_orig = r[10] if len(r) > 10 else ""
        unidad = r[13] if len(r) > 13 else "Kg"
        envase_orig = r[14] if len(r) > 14 else ""
        cantidad_raw = r[12] if len(r) > 12 else "0"

        if not caracteristica_orig:
            inconsistencias["caracteristicas_vacias"] += 1
        if not envase_orig:
            inconsistencias["envases_vacios"] += 1
        if unidad.upper() == "L":
            inconsistencias["registros_en_litros"] += 1
        else:
            inconsistencias["registros_en_kg"] += 1

        try:
            cant_float = float(cantidad_raw.replace(',', '.'))
        except ValueError:
            cant_float = 1.0

        # Simulación de peso bruto en gramos (convertir Kg -> g)
        peso_bruto_g = cant_float * 1000.0 if unidad.upper() != "G" else cant_float

        # Reclasificación mediante el motor CLARA+
        req = EntradaResiduoRequest(
            dependencia=cabecera["dependencia"],
            laboratorio=cabecera["laboratorio"],
            actividad="Muestreo histórico",
            responsable=cabecera["responsable"],
            fecha="2026-08-11",
            descripcion=nombre_residuo,
            insumos=[nombre_residuo],
            estado_fisico="Líquido" if unidad.upper() == "L" else "Sólido",
            peso_bruto_g=peso_bruto_g,
            tara_g=200.0
        )

        clasificacion_clara = clasificar_residuo(req)

        residuos_procesados.append({
            "id_residuo": id_res,
            "id_registro": id_reg,
            "dependencia": cabecera["dependencia"],
            "laboratorio": cabecera["laboratorio"],
            "nombre_original": nombre_residuo,
            "caracteristica_original": caracteristica_orig,
            "unidad_original": unidad,
            "envase_original": envase_orig,
            "clasificacion_clara": clasificacion_clara.model_dump()
        })

    return {
        "total_registros_cabecera": len(registros_map),
        "total_residuos_procesados": len(residuos_procesados),
        "diagnostico_inconsistencias": inconsistencias,
        "muestra_residuos": residuos_procesados[:5]
    }
