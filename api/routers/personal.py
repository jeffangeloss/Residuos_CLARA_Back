"""Padrón de personal: la identidad que sustituye al texto libre.

Los dos formularios de Google recogían el correo automáticamente, pero en el
Excel exportado esa columna está vacía en las 856 filas. Los nombres se
escribieron a mano y se multiplicaron. El problema no es de seguridad: es de
padrón, y se resuelve con un catálogo, no con contraseñas.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from api.serializadores import serializar_persona
from core.database import get_db
from core.models import PersonaRequest, RolPadron
from core.repositorio import filtrar_personal, registrar_persona
from core.response import success_response

router = APIRouter(prefix="/api/v1/personal", tags=["personal"])


@router.get("")
def listar_personal(
    rol: Optional[RolPadron] = Query(None, description="encargado, csbqr o generador"),
    dependencia: Optional[str] = Query(None, max_length=100),
    buscar: Optional[str] = Query(None, max_length=150),
    db: Session = Depends(get_db),
):
    """Padrón para los desplegables de la app.

    Cada entrada trae sus variantes conocidas, de modo que buscar por
    cualquiera de ellas encuentra a la persona correcta.
    """
    personas = filtrar_personal(db, rol=rol, dependencia=dependencia, busqueda=buscar)
    return success_response(
        message=f"{len(personas)} personas en el padrón",
        data=[serializar_persona(persona) for persona in personas],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def dar_de_alta_persona(peticion: PersonaRequest, db: Session = Depends(get_db)):
    """Da de alta a alguien que no estaba en el padrón.

    El catálogo no es cerrado, por la misma razón que el de laboratorios:
    bloquear lo que no esté sembrado impediría declaraciones legítimas. Lo que
    entra por aquí queda marcado como no oficial, visible para el CSBQR.
    """
    persona = registrar_persona(
        db,
        nombre=peticion.nombre,
        dependencia=peticion.dependencia,
        correo=peticion.correo,
        telefono=peticion.telefono,
        es_encargado=peticion.es_encargado,
        es_csbqr=peticion.es_csbqr,
        es_generador=peticion.es_generador,
    )
    return success_response(
        message=f"{persona.nombre} está en el padrón",
        data=serializar_persona(persona),
    )
