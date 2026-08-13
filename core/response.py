"""
Standardized API Response Envelope - Inspired by backend_v3 architecture
"""

from typing import Generic, TypeVar, Optional, Any
from pydantic import BaseModel

T = TypeVar("T")

class APIResponse(BaseModel, Generic[T]):
    message: str
    data: Optional[T] = None
    success: bool = True
    error: Optional[str] = None
    meta: Optional[dict] = None

def success_response(message: str, data: Any = None, meta: dict = None) -> dict:
    """Envoltorio estándar. `meta` transporta paginación y totales.

    Los datos siguen viajando en `data` sin envolverse en otro objeto para no
    romper a los clientes que ya consumen la lista directamente.
    """
    respuesta = {
        "message": message,
        "data": data,
        "success": True,
        "error": None
    }
    if meta is not None:
        respuesta["meta"] = meta
    return respuesta

def error_response(message: str, error: str = None, data: Any = None) -> dict:
    return {
        "message": message,
        "data": data,
        "success": False,
        "error": error or message
    }
