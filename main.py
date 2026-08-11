"""
CLARA+ FastAPI Backend API
Universidad de Lima - CSBQR
Plataforma Unificada de Clasificación, Rotulado y Declaración de Residuos Peligrosos
"""

import os
import traceback
from fastapi import FastAPI, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from core.models import EntradaResiduoRequest, ResultadoClasificacion
from core.classifier import clasificar_residuo, PARES_PROHIBIDOS
from core.migrador_excel import parsear_base_historica
from core.response import success_response, error_response
from typing import List

app = FastAPI(
    title="CLARA+ API - Residuos Peligrosos ULima",
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

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="Ocurrió un error interno en el servidor",
            error=str(exc)
        )
    )

@app.get("/")
def read_root():
    return success_response(
        message="Servicio CLARA+ Residuos Peligrosos API disponible",
        data={
            "system": "CLARA+ ULima Residuos Peligrosos API",
            "version": "1.0.0",
            "ontologia": "Ontología Canónica ULima v2 (15 categorías)",
            "matriz": "Matriz de Incompatibilidad CSBQR 11x11"
        }
    )

@app.get("/health")
def health_check():
    return success_response(message="Estado del servicio OK", data={"status": "healthy"})

@app.post("/api/v1/clasificar")
def clasificar(entrada: EntradaResiduoRequest):
    """
    Ejecuta el motor determinista de ontología ULima (15 categorías de residuos peligrosos).
    """
    try:
        resultado = clasificar_residuo(entrada)
        return success_response(
            message="Residuo peligros clasificado exitosamente",
            data=resultado.model_dump()
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response(
                message="Error al clasificar el residuo peligroso",
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

@app.get("/api/v1/historico/benchmark")
def diagnostico_historico():
    """
    Procesa y reclasifica los 856 residuos reales de DB_DeclaraciónResiduosPeligrosos.xlsx.
    """
    excel_path = "/Users/jjjangelosss/ResiduosCLARA+/DB_DeclaraciónResiduosPeligrosos.xlsx"
    if not os.path.exists(excel_path):
        raise HTTPException(status_code=404, detail="Archivo DB_DeclaraciónResiduosPeligrosos.xlsx no encontrado")
    
    reporte = parsear_base_historica(excel_path)
    return success_response(
        message="Diagnóstico y reclasificación de la base histórica de 856 residuos completado",
        data=reporte
    )
