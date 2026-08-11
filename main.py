"""
CLARA+ FastAPI Backend API
Universidad de Lima - CSBQR
Patrones de desarrollo inspirados en backend_v3 & CORE V3
"""

import traceback
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from core.models import EntradaResiduoRequest, ResultadoClasificacion
from core.classifier import clasificar_residuo, PARES_PROHIBIDOS
from core.response import success_response, error_response
from typing import List

app = FastAPI(
    title="CLARA+ API",
    description="API de Clasificación, Rotulado, Incompatibilidad y Declaración Oficial de Residuos Peligrosos",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom Global Exception Handler (Patrón backend_v3)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="Ocurrió un error en el servidor",
            error=str(exc)
        )
    )

@app.get("/")
def read_root():
    return success_response(
        message="Servicio CLARA+ Backend API disponible",
        data={
            "system": "CLARA+ ULima Backend API",
            "version": "1.0.0",
            "architecture": "backend_v3 modular design + CORE V3 grams canonical unit"
        }
    )

@app.get("/health")
def health_check():
    return success_response(message="Estado del servicio OK", data={"status": "healthy"})

@app.post("/api/v1/clasificar")
def clasificar(entrada: EntradaResiduoRequest):
    """
    Ejecuta el motor determinista de ontología ULima (15 categorías).
    Respuesta estandarizada tipo backend_v3.
    """
    try:
        resultado = clasificar_residuo(entrada)
        return success_response(
            message="Residuo clasificado exitosamente",
            data=resultado.model_dump()
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response(
                message="Error al clasificar el residuo",
                error=str(e)
            )
        )

@app.post("/api/v1/acopio/verificar")
def verificar_acopio(grupos: List[str]):
    """
    Evalúa incompatibilidad entre residuos en el punto de acopio.
    """
    try:
        grupos_upper = [g.upper() for g in grupos]
        conflictos = []
        
        for i in range(len(grupos_upper)):
            for j in range(i + 1, len(grupos_upper)):
                a, b = grupos_upper[i], grupos_upper[j]
                for p1, p2, razon in PARES_PROHIBIDOS:
                    if (a == p1 and b == p2) or (a == p2 and b == p1):
                        conflictos.append({"a": a, "b": b, "veredicto": "NUNCA", "razon": razon})

        if conflictos:
            return success_response(
                message="Incompatibilidad grave detectada. No juntar residuos.",
                data={"veredicto": "NUNCA", "conflictos": conflictos}
            )
        elif len(set(grupos_upper)) > 1:
            return success_response(
                message="Residuos requieren segregación en distintas bandejas.",
                data={"veredicto": "SEGREGAR", "razon": "Grupos químicos distintos."}
            )
        else:
            return success_response(
                message="Residuos compatibles en el mismo punto de acopio.",
                data={"veredicto": "COMPATIBLE", "razon": "Mismo grupo químico."}
            )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message="Error al verificar compatibilidad de acopio",
                error=str(e)
            )
        )
