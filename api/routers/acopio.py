"""Verificación de compatibilidad en el punto de acopio."""

import traceback

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List

from core.database import get_db
from core.repositorio import evaluar_compatibilidad
from core.response import error_response, success_response

router = APIRouter(prefix="/api/v1/acopio", tags=["acopio"])

MENSAJES = {
    "NUNCA": "Incompatibilidad grave detectada. No juntar residuos.",
    "SEGREGAR": "Residuos requieren segregación en distintas bandejas.",
    "COMPATIBLE": "Residuos compatibles en el mismo punto de acopio.",
}


@router.post("/verificar")
def verificar_acopio(grupos: List[str], db: Session = Depends(get_db)):
    """Evalúa incompatibilidad entre residuos en el punto de acopio.

    La matriz se lee de la tabla `reglas_incompatibilidad`, que es la fuente de
    verdad persistida; el módulo del clasificador solo la siembra. El veredicto
    es el **almacenado**, no uno derivado en tiempo de ejecución: derivarlo era
    lo que dejaba 24 combinaciones peligrosas como SEGREGAR en vez de NUNCA.
    """
    try:
        veredicto = evaluar_compatibilidad(db, grupos)
        return success_response(
            message=MENSAJES[veredicto["veredicto"]],
            data=veredicto,
        )
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message="Error al verificar compatibilidad de acopio",
                error=str(exc),
            ),
        )
