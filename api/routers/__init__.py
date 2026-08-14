"""Registro central de los routers de la API.

Un router por funcionalidad, como los blueprints de `backend_v3` y los módulos
de `ULima_Backend_IS2`. Antes todo esto vivía en un `main.py` de casi 900
líneas donde la exportación de Excel, el padrón y el ciclo de vida del residuo
estaban intercalados.

El orden importa en un caso: `/api/v1/declaraciones/{id}/...` tiene que
registrarse antes que cualquier ruta que pudiera capturar el mismo prefijo.
"""

from fastapi import FastAPI

from api.routers import (
    acopio,
    catalogos,
    declaraciones,
    exportacion,
    fotos,
    personal,
    registros,
    salud,
)

ROUTERS = [
    salud.router,
    registros.router,
    declaraciones.router,
    catalogos.router,
    personal.router,
    fotos.router,
    acopio.router,
    exportacion.router,
]


def registrar_routers(app: FastAPI) -> None:
    for router in ROUTERS:
        app.include_router(router)
