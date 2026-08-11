"""
CLARA+ FastAPI Backend API
Universidad de Lima - CSBQR
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "CLARA+ ULima Backend API",
        "version": "1.0.0"
    }

@app.get("/health")
def health_check():
    return {"status": "ok"}
