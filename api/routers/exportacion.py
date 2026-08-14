"""Salidas oficiales: Excel de declaración, de traslado y etiqueta PDF.

Son las funciones que jubilan a `respel_app.py`, la app de escritorio que leía
el Google Sheet con una cuenta de servicio y rellenaba las plantillas a mano.
"""

import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.artifacts import etiqueta_pdf, workbook_declaracion, workbook_traslado
from core.database import get_db
from core.migrador_excel import parsear_base_historica
from core.repositorio import consulta_declaraciones, declaraciones_del_periodo
from core.response import success_response

router = APIRouter(prefix="/api/v1", tags=["exportacion"])

EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/exportar/declaracion")
def exportar_declaracion(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    residuo_id: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Genera el Excel de declaración para un período o una selección de residuos."""
    if residuo_id:
        records = consulta_declaraciones(db, residuo_id).all()
    else:
        records = declaraciones_del_periodo(db, month, year)

    if not records:
        raise HTTPException(
            status_code=404,
            detail="No hay declaraciones para el período o selección indicada",
        )

    contenido = workbook_declaracion(records, month, year)
    nombre = f"Declaracion_{month:02d}_{year}.xlsx"
    return StreamingResponse(
        contenido,
        media_type=EXCEL,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/exportar/traslado")
def exportar_traslado(
    residuo_id: List[str] = Query(..., min_length=1),
    transportista: str = Query(..., min_length=1, max_length=150),
    db: Session = Depends(get_db),
):
    """Genera el formato Excel de traslado para residuos seleccionados."""
    records = consulta_declaraciones(db, residuo_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No se encontraron los residuos seleccionados")

    contenido = workbook_traslado(records, transportista)
    return StreamingResponse(
        contenido,
        media_type=EXCEL,
        headers={"Content-Disposition": 'attachment; filename="Traslado_CLARA.xlsx"'},
    )


@router.get("/etiqueta/{id_residuo}/pdf")
def obtener_etiqueta_pdf(id_residuo: str, db: Session = Depends(get_db)):
    """Genera una etiqueta PDF de 10x15 cm para una declaración persistida."""
    record = consulta_declaraciones(db, [id_residuo]).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    contenido = etiqueta_pdf(record)
    return StreamingResponse(
        contenido,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiqueta-{id_residuo}.pdf"'},
    )


@router.get("/historico/benchmark")
def diagnostico_historico():
    """Reclasifica los 856 residuos reales de la base histórica y reporta el resultado."""
    ruta = os.getenv("HISTORICAL_EXCEL_PATH")
    if not ruta:
        raise HTTPException(
            status_code=503,
            detail="HISTORICAL_EXCEL_PATH no está configurado para el benchmark histórico",
        )
    if not os.path.exists(ruta):
        raise HTTPException(
            status_code=404,
            detail="Archivo DB_DeclaraciónResiduosPeligrosos.xlsx no encontrado",
        )

    return success_response(
        message="Diagnóstico y reclasificación de la base histórica de 856 residuos completado",
        data=parsear_base_historica(ruta),
    )
