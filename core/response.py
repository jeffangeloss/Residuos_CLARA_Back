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

def success_response(message: str, data: Any = None) -> dict:
    return {
        "message": message,
        "data": data,
        "success": True,
        "error": None
    }

def error_response(message: str, error: str = None, data: Any = None) -> dict:
    return {
        "message": message,
        "data": data,
        "success": False,
        "error": error or message
    }
