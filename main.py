"""
CLARA+ FastAPI Backend API
Universidad de Lima - CSBQR
Alineado a las buenas prácticas de desarrollo de CORE V3
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from core.models import EntradaResiduoRequest, ResultadoClasificacion, MovimientoKardexRequest
from core.classifier import clasificar_residuo, PARES_PROHIBIDOS
from typing import List

app = FastAPI(
    title="CLARA+ API",
    description="API de Clasificación, Rotulado, Incompatibilidad y Declaración Oficial de Residuos Peligrosos (Alineado a CORE V3)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "CLARA+ ULima Backend API",
        "version": "1.0.0",
        "core_version": "V3 (Gramos canónicos + Incompatibilidad CSBQR 11x11)"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/v1/clasificar", response_model=ResultadoClasificacion)
def clasificar(entrada: EntradaResiduoRequest):
    """
    Ejecuta el motor determinista de ontología ULima (15 categorías).
    Guarda peso en GRAMOS y calcula KG en un solo lugar.
    """
    try:
        resultado = clasificar_residuo(entrada)
        return resultado
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error en la clasificación del residuo: {str(e)}"
        )

@app.post("/api/v1/acopio/verificar")
def verificar_acopio(grupos: List[str]):
    """
    Evalúa incompatibilidad entre residuos en el punto de acopio.
    """
    grupos_upper = [g.upper() for g in grupos]
    conflictos = []
    
    for i in range(len(grupos_upper)):
        for j in range(i + 1, len(grupos_upper)):
            a, b = grupos_upper[i], grupos_upper[j]
            for p1, p2, razon in PARES_PROHIBIDOS:
                if (a == p1 and b == p2) or (a == p2 and b == p1):
                    conflictos.append({"a": a, "b": b, "veredicto": "NUNCA", "razon": razon})

    if conflictos:
        return {"veredicto": "NUNCA", "conflictos": conflictos}
    elif len(set(grupos_upper)) > 1:
        return {"veredicto": "SEGREGAR", "razon": "Grupos químicos distintos: almacenar en bandejas de contención separadas."}
    else:
        return {"veredicto": "COMPATIBLE", "razon": "Residuos del mismo grupo de compatibilidad."}
