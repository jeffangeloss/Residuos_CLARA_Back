"""Registros: la cabecera de una visita, con todos sus residuos colgando.

Es el corazón de lo que sustituye al circuito de dos formularios de Google. La
cabecera se llena una vez y contra ella se declaran todos los envases, sin
esperar el correo con el código para pegarlo en cada uno.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.serializadores import serializar_registro
from core.classifier import clasificar_residuo
from core.database import get_db
from core.models import EntradaResiduoRequest, RegistroRequest, ResiduoDeRegistroRequest
from core.repositorio import (
    DatoMaestroFaltante,
    buscar_registro,
    crear_declaracion,
    crear_registro,
    filtrar_registros,
)
from core.response import error_response, success_response

router = APIRouter(prefix="/api/v1/registros", tags=["registros"])


@router.post("", status_code=status.HTTP_201_CREATED)
def abrir_registro(peticion: RegistroRequest, db: Session = Depends(get_db)):
    """Abre la cabecera de una visita.

    Contra el código devuelto se declaran después todos los residuos, sin
    repetir dependencia, laboratorio ni responsable en cada uno.
    """
    registro = crear_registro(
        db,
        dependencia=peticion.dependencia,
        laboratorio=peticion.laboratorio,
        responsable_encargado=peticion.responsable_encargado,
        fecha=peticion.fecha,
        elaborado_por=peticion.elaborado_por,
        telefono_contacto=peticion.telefono_contacto,
        comentarios_generales=peticion.comentarios_generales,
    )
    return success_response(
        message=f"Registro {registro.codigo} abierto",
        data=serializar_registro(registro),
    )


@router.get("")
def listar_registros(
    month: Optional[int] = Query(None, ge=1, le=12, description="Requiere year"),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    laboratorio: Optional[str] = Query(None, max_length=100),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Historial de visitas, de la más reciente a la más antigua."""
    if month is not None and year is None:
        raise HTTPException(status_code=422, detail="El filtro 'month' requiere también 'year'")

    registros, total = filtrar_registros(
        db, mes=month, anio=year, laboratorio=laboratorio,
        limite=limit, desplazamiento=offset,
    )
    return success_response(
        message=f"Se recuperaron {len(registros)} de {total} registros",
        data=[serializar_registro(r) for r in registros],
        meta={"total": total, "limit": limit, "offset": offset},
    )


@router.get("/{id_registro}")
def obtener_registro(id_registro: str, db: Session = Depends(get_db)):
    """Cabecera de la visita con todos sus residuos declarados."""
    registro = buscar_registro(db, id_registro)
    if not registro:
        raise HTTPException(status_code=404, detail=f"Registro no encontrado: {id_registro}")

    return success_response(
        message=f"Registro {id_registro} con {len(registro.declaraciones)} residuos",
        data=serializar_registro(registro, incluir_residuos=True),
    )


@router.post("/{id_registro}/residuos", status_code=status.HTTP_201_CREATED)
def declarar_residuo(
    id_registro: str,
    peticion: ResiduoDeRegistroRequest,
    db: Session = Depends(get_db),
):
    """Declara un residuo dentro de una visita ya abierta.

    Es el flujo que sustituye al circuito de dos formularios: la cabecera se
    llena una vez y aquí solo viajan los datos propios del envase.
    """
    registro = buscar_registro(db, id_registro)
    if not registro:
        raise HTTPException(status_code=404, detail=f"Registro no encontrado: {id_registro}")

    entrada = EntradaResiduoRequest(
        dependencia=registro.laboratorio.dependencia.nombre,
        laboratorio=registro.laboratorio.nombre,
        elaborado_por=registro.elaborado_por,
        fecha=peticion.fecha or registro.fecha,
        **peticion.model_dump(exclude={"fecha"}),
    )
    resultado = clasificar_residuo(entrada)

    try:
        crear_declaracion(db, entrada, resultado, registro=registro)
    except DatoMaestroFaltante as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_response(
                message="Los datos maestros de la base no están sincronizados con la ontología",
                error=str(exc),
            ),
        )

    return success_response(
        message=f"Residuo declarado en el registro {id_registro}",
        data=resultado.model_dump(mode="json"),
    )
