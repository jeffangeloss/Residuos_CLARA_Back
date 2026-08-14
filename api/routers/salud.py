"""Estado del servicio: qué versión corre y contra qué base."""

from fastapi import APIRouter

from core.response import success_response

router = APIRouter(tags=["salud"])

MOTOR = "PostgreSQL"


@router.get("/")
def raiz():
    return success_response(
        message=f"Servicio CLARA+ Residuos Peligrosos API disponible ({MOTOR})",
        data={
            "system": "CLARA+ ULima Residuos Peligrosos API",
            "version": "2.0.0 (3FN)",
            "database": MOTOR,
            "ontologia": "Ontología Canónica ULima v2 (15 categorías)",
            "matriz": "Matriz de Incompatibilidad CSBQR 11x11",
        },
    )


@router.get("/health")
def salud():
    return success_response(
        message="Estado del servicio OK",
        data={"status": "healthy", "database": MOTOR},
    )
