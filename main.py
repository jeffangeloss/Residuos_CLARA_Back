"""CLARA+ API — Residuos Peligrosos ULima (CSBQR).

Este archivo solo arma la aplicación: middleware, manejo de errores y el
registro de los routers. Cada funcionalidad vive en su propio módulo bajo
`api/routers/`, y la lógica de dominio y persistencia en `core/`.

El esquema se crea y versiona con Alembic (`alembic upgrade head`), no al
importar este módulo: crear tablas en el arranque hacía divergir la base real
de las migraciones y dejaba cambios de esquema sin historial.
"""

import os
import traceback

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import core.entorno  # noqa: F401  Carga el .env antes de leer nada del entorno.
from api.routers import registrar_routers
from api.routers.salud import MOTOR
from core.response import error_response

app = FastAPI(
    title="CLARA+ API - Residuos Peligrosos ULima (3FN PostgreSQL)",
    description=(
        "API de clasificación, rotulado, incompatibilidad y declaración, "
        "sobre un esquema relacional 3FN"
    ),
    version="2.0.0",
)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def manejador_global(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="Ocurrió un error interno en el servidor",
            error=str(exc),
        ),
    )


registrar_routers(app)


if __name__ == "__main__":
    import uvicorn

    entorno = os.getenv("APP_ENV", "development").lower()
    print(f"CLARA+ API sobre {MOTOR} — entorno {entorno}")
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=entorno == "development",
    )
