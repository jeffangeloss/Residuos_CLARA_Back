"""Declaraciones: consulta, ciclo de vida, kardex y revisión de la clasificación."""

import traceback
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from api.routers.salud import MOTOR
from api.serializadores import serializar_declaracion, serializar_movimiento
from core.classifier import clasificar_residuo
from core.database import get_db
from core.models import (
    CambioEstadoRequest,
    ConfirmacionCategoriaRequest,
    EntradaResiduoRequest,
    EstadoResiduo,
)
from core.repositorio import (
    DatoMaestroFaltante,
    TransicionInvalida,
    buscar_declaracion,
    cambiar_estado,
    confirmar_clasificacion,
    crear_declaracion,
    filtrar_declaraciones,
    kardex_de,
)
from core.response import error_response, success_response

router = APIRouter(prefix="/api/v1", tags=["declaraciones"])


@router.post("/clasificar")
def clasificar(entrada: EntradaResiduoRequest, db: Session = Depends(get_db)):
    """Clasifica y persiste un residuo resolviendo o abriendo su registro.

    Es el camino heredado, anterior a la estructura maestro-detalle: recibe la
    cabecera repetida en cada residuo. Se conserva para que ningún cliente se
    rompa; la captura nueva usa `POST /registros/{id}/residuos`.
    """
    resultado = clasificar_residuo(entrada)

    try:
        crear_declaracion(db, entrada, resultado)
    except DatoMaestroFaltante as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_response(
                message="Los datos maestros de la base no están sincronizados con la ontología",
                error=str(exc),
            ),
        )
    except Exception as exc:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=error_response(
                message="Error al clasificar y guardar el residuo en PostgreSQL (3FN)",
                error=str(exc),
            ),
        )

    return success_response(
        message=f"Residuo clasificado y persistido en el esquema 3FN ({MOTOR})",
        data=resultado.model_dump(mode="json"),
    )


@router.get("/declaraciones")
def listar_declaraciones(
    month: Optional[int] = Query(None, ge=1, le=12, description="Requiere year"),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    laboratorio: Optional[str] = Query(None, max_length=100),
    categoria_id: Optional[str] = Query(None, max_length=50),
    estado: Optional[EstadoResiduo] = Query(None),
    escalar_csbqr: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Historial de declaraciones con los filtros de la RF-08.

    Sin parámetros devuelve la primera página del historial completo, de modo
    que los clientes existentes siguen funcionando sin cambios.
    """
    if month is not None and year is None:
        raise HTTPException(
            status_code=422, detail="El filtro 'month' requiere también 'year'"
        )

    declaraciones, total = filtrar_declaraciones(
        db,
        mes=month,
        anio=year,
        laboratorio=laboratorio,
        categoria_id=categoria_id,
        estado=estado.value if estado else None,
        escalar_csbqr=escalar_csbqr,
        limite=limit,
        desplazamiento=offset,
    )

    records = [serializar_declaracion(declaracion) for declaracion in declaraciones]

    return success_response(
        message=f"Se recuperaron {len(records)} de {total} declaraciones desde {MOTOR}",
        data=records,
        meta={"total": total, "limit": limit, "offset": offset},
    )


@router.post("/declaraciones/{id_residuo}/escalar")
def escalar_declaracion(id_residuo: str, db: Session = Depends(get_db)):
    """Registra explícitamente que una declaración requiere atención del CSBQR."""
    record = buscar_declaracion(db, id_residuo)
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    record.escalar_csbqr = True
    db.commit()
    return success_response(
        message="La declaración fue marcada para atención del CSBQR",
        data={"id_residuo": id_residuo, "escalar_csbqr": True},
    )


@router.post("/declaraciones/{id_residuo}/estado")
def cambiar_estado_declaracion(
    id_residuo: str,
    peticion: CambioEstadoRequest,
    db: Session = Depends(get_db),
):
    """Avanza el ciclo de vida del residuo y registra el movimiento de kardex.

    El estado y su movimiento se confirman en la misma transacción: no puede
    figurar un residuo trasladado sin el movimiento que lo respalda.
    """
    record = buscar_declaracion(db, id_residuo)
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    estado_anterior = record.estado
    try:
        movimiento = cambiar_estado(db, record, peticion)
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return success_response(
        message=f"Residuo {id_residuo}: {estado_anterior} → {record.estado}",
        data={
            "id_residuo": id_residuo,
            "estado_anterior": estado_anterior,
            "estado": record.estado,
            "movimiento": serializar_movimiento(movimiento),
        },
    )


@router.post("/declaraciones/{id_residuo}/categoria")
def confirmar_categoria(
    id_residuo: str,
    peticion: ConfirmacionCategoriaRequest,
    db: Session = Depends(get_db),
):
    """Acepta o corrige la categoría que propuso el clasificador.

    El Gem dice de su propia salida que "es una ayuda técnica interna; no
    reemplaza la clasificación legal ni la decisión del CSBQR". Esto es lo que
    hace que la app funcione igual: propone, y una persona decide.

    La propuesta original se conserva pase lo que pase, para poder medir
    después cuánto acierta el clasificador con residuos reales.
    """
    record = buscar_declaracion(db, id_residuo)
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    propuesta = record.categoria_propuesta_id

    try:
        confirmar_clasificacion(db, record, peticion)
    except TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except DatoMaestroFaltante as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    corregida = propuesta is not None and propuesta != record.categoria_id
    return success_response(
        message=(
            f"Clasificación de {id_residuo} corregida a {record.categoria.nombre}"
            if corregida
            else f"Clasificación de {id_residuo} confirmada"
        ),
        data=serializar_declaracion(record),
    )


@router.get("/declaraciones/{id_residuo}/kardex")
def obtener_kardex(id_residuo: str, db: Session = Depends(get_db)):
    """Traza de custodia completa del residuo, en orden cronológico."""
    record = buscar_declaracion(db, id_residuo)
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    movimientos = kardex_de(db, record)
    return success_response(
        message=f"El residuo {id_residuo} tiene {len(movimientos)} movimientos registrados",
        data={
            "id_residuo": id_residuo,
            "estado": record.estado,
            "movimientos": [serializar_movimiento(m) for m in movimientos],
        },
    )
