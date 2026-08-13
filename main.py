"""
CLARA+ FastAPI Backend API
Universidad de Lima - CSBQR
Plataforma Unificada con Esquema Relacional 3FN en PostgreSQL
"""

import os
import traceback
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status, Request, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from core.models import (
    CambioEstadoRequest,
    EntradaResiduoRequest,
    EstadoResiduo,
    RegistroRequest,
    ResiduoDeRegistroRequest,
)
from core.classifier import clasificar_residuo
from core.migrador_excel import parsear_base_historica
from core.response import success_response, error_response
from core.database import get_db, DATABASE_URL
from core.db_models import DeclaracionResiduoDB
from core.repositorio import (
    DatoMaestroFaltante,
    TransicionInvalida,
    buscar_declaracion,
    buscar_registro,
    cambiar_estado,
    consulta_declaraciones,
    crear_declaracion,
    crear_registro,
    declaraciones_del_periodo,
    evaluar_compatibilidad,
    filtrar_declaraciones,
    filtrar_registros,
    kardex_de,
)
from core.artifacts import workbook_declaracion, workbook_traslado, etiqueta_pdf

DATABASE_ENGINE = "SQLite (desarrollo)" if DATABASE_URL.startswith("sqlite") else "PostgreSQL"

# El esquema se crea y versiona con Alembic (`alembic upgrade head`), no al
# importar este módulo. Crear tablas en el arranque hacía divergir la base real
# de las migraciones y dejaba cambios de esquema sin historial.

app = FastAPI(
    title="CLARA+ API - Residuos Peligrosos ULima (3FN PostgreSQL)",
    description="API de Clasificación, Rotulado, Incompatibilidad y Declaración con Base de Datos 3FN Normalizada",
    version="2.0.0"
)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
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
async def global_exception_handler(request: Request, exc: Exception):
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_response(
            message="Ocurrió un error interno en el servidor",
            error=str(exc)
        )
    )

@app.get("/")
def read_root():
    return success_response(
        message=f"Servicio CLARA+ Residuos Peligrosos API disponible ({DATABASE_ENGINE})",
        data={
            "system": "CLARA+ ULima Residuos Peligrosos API",
            "version": "2.0.0 (3FN)",
            "database": DATABASE_ENGINE,
            "ontologia": "Ontología Canónica ULima v2 (15 categorías)",
            "matriz": "Matriz de Incompatibilidad CSBQR 11x11"
        }
    )

@app.get("/health")
def health_check():
    return success_response(message="Estado del servicio OK", data={"status": "healthy", "database": DATABASE_ENGINE})

@app.post("/api/v1/clasificar")
def clasificar(entrada: EntradaResiduoRequest, db: Session = Depends(get_db)):
    """
    Ejecuta el motor determinista de ontología ULima (15 categorías)
    y guarda la declaración normalizada (3FN) en PostgreSQL.
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
                error=str(exc)
            )
        )

    return success_response(
        message=f"Residuo clasificado y persistido en el esquema 3FN ({DATABASE_ENGINE})",
        data=resultado.model_dump(mode="json")
    )

def _serializar_declaracion(declaracion: DeclaracionResiduoDB) -> dict:
    registro = declaracion.registro
    laboratorio = declaracion.laboratorio
    categoria = declaracion.categoria
    return {
        "id_residuo": declaracion.codigo_residuo,
        "codigo_formato": declaracion.codigo_formato,
        "id_registro": registro.codigo if registro else None,
        "responsable_encargado": registro.responsable_encargado if registro else None,
        "elaborado_por": registro.elaborado_por if registro else None,
        "dependencia": laboratorio.dependencia.nombre if laboratorio and laboratorio.dependencia else None,
        "laboratorio": laboratorio.nombre if laboratorio else None,
        "actividad": declaracion.actividad,
        "fecha": declaracion.fecha.isoformat(),
        "descripcion": declaracion.descripcion,
        "insumos": [insumo.nombre_quimico for insumo in declaracion.insumos],
        "pictogramas_ghs": [p.codigo_pictograma for p in declaracion.pictogramas],
        "observaciones": [o.texto for o in declaracion.observaciones],
        "cantidad": declaracion.cantidad,
        "unidad": declaracion.unidad,
        "modo_medicion": declaracion.modo_medicion,
        "peso_neto_g": declaracion.peso_neto_g,
        # Solo tiene valor cuando la cantidad es una masa en kilogramos. En un
        # residuo declarado por volumen no existe tal cifra.
        "peso_neto_kg": declaracion.cantidad if declaracion.unidad == "Kg" else None,
        "categoria_nombre": categoria.nombre if categoria else None,
        "nombre_normalizado": declaracion.nombre_normalizado,
        "clase_sunat": categoria.clase_sunat if categoria else None,
        "clase_basilea": categoria.clase_basilea if categoria else None,
        "grupo_compatibilidad": categoria.grupo_compatibilidad if categoria else "AISLAR",
        "confianza": declaracion.confianza,
        "estado": declaracion.estado,
        "escalar_csbqr": declaracion.escalar_csbqr,
        "creado_en": declaracion.creado_en.isoformat() if declaracion.creado_en else None
    }

def _serializar_registro(registro, incluir_residuos: bool = False) -> dict:
    laboratorio = registro.laboratorio
    datos = {
        "id_registro": registro.codigo,
        "dependencia": laboratorio.dependencia.nombre if laboratorio and laboratorio.dependencia else None,
        "laboratorio": laboratorio.nombre if laboratorio else None,
        "responsable_encargado": registro.responsable_encargado,
        "elaborado_por": registro.elaborado_por,
        "fecha": registro.fecha.isoformat(),
        "telefono_contacto": registro.telefono_contacto,
        "comentarios_generales": registro.comentarios_generales,
        "total_residuos": len(registro.declaraciones),
        "creado_en": registro.creado_en.isoformat() if registro.creado_en else None,
    }
    if incluir_residuos:
        datos["residuos"] = [
            _serializar_declaracion(d)
            for d in sorted(registro.declaraciones, key=lambda d: d.id)
        ]
    return datos


@app.post("/api/v1/registros", status_code=status.HTTP_201_CREATED)
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
        data=_serializar_registro(registro),
    )


@app.get("/api/v1/registros")
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
        data=[_serializar_registro(r) for r in registros],
        meta={"total": total, "limit": limit, "offset": offset},
    )


@app.get("/api/v1/registros/{id_registro}")
def obtener_registro(id_registro: str, db: Session = Depends(get_db)):
    """Cabecera de la visita con todos sus residuos declarados."""
    registro = buscar_registro(db, id_registro)
    if not registro:
        raise HTTPException(status_code=404, detail=f"Registro no encontrado: {id_registro}")

    return success_response(
        message=f"Registro {id_registro} con {len(registro.declaraciones)} residuos",
        data=_serializar_registro(registro, incluir_residuos=True),
    )


@app.post("/api/v1/registros/{id_registro}/residuos", status_code=status.HTTP_201_CREATED)
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


@app.get("/api/v1/declaraciones")
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
    """
    Historial de declaraciones con los filtros de la RF-08.

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

    records = [_serializar_declaracion(declaracion) for declaracion in declaraciones]

    return success_response(
        message=f"Se recuperaron {len(records)} de {total} declaraciones desde {DATABASE_ENGINE}",
        data=records,
        meta={"total": total, "limit": limit, "offset": offset},
    )


@app.get("/api/v1/exportar/declaracion")
def exportar_declaracion(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    residuo_id: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Genera el Excel de declaración para un período o una selección de residuos."""
    if residuo_id:
        records = consulta_declaraciones(db, residuo_id).all()
    else:
        records = declaraciones_del_periodo(db, month, year)

    if not records:
        raise HTTPException(status_code=404, detail="No hay declaraciones para el período o selección indicada")

    content = workbook_declaracion(records, month, year)
    filename = f"Declaracion_{month:02d}_{year}.xlsx"
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/v1/exportar/traslado")
def exportar_traslado(
    residuo_id: List[str] = Query(..., min_length=1),
    transportista: str = Query(..., min_length=1, max_length=150),
    db: Session = Depends(get_db),
):
    """Genera el formato Excel de traslado para residuos seleccionados."""
    records = consulta_declaraciones(db, residuo_id).all()
    if not records:
        raise HTTPException(status_code=404, detail="No se encontraron los residuos seleccionados")

    content = workbook_traslado(records, transportista)
    return StreamingResponse(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Traslado_CLARA.xlsx"'},
    )


@app.get("/api/v1/etiqueta/{id_residuo}/pdf")
def obtener_etiqueta_pdf(id_residuo: str, db: Session = Depends(get_db)):
    """Genera una etiqueta PDF de 10x15 cm para una declaración persistida."""
    record = consulta_declaraciones(db, [id_residuo]).first()
    if not record:
        raise HTTPException(status_code=404, detail=f"Residuo no encontrado: {id_residuo}")

    content = etiqueta_pdf(record)
    return StreamingResponse(
        content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiqueta-{id_residuo}.pdf"'},
    )


@app.post("/api/v1/declaraciones/{id_residuo}/escalar")
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


def _serializar_movimiento(movimiento) -> dict:
    return {
        "id": movimiento.id,
        "tipo_movimiento": movimiento.tipo_movimiento,
        "motivo": movimiento.motivo,
        "cantidad_g": movimiento.cantidad_g,
        "laboratorio_origen": (
            movimiento.laboratorio_origen.nombre if movimiento.laboratorio_origen else None
        ),
        "laboratorio_destino": (
            movimiento.laboratorio_destino.nombre if movimiento.laboratorio_destino else None
        ),
        "registrado_por": movimiento.registrado_por,
        "registrado_en": movimiento.registrado_en.isoformat(),
        "observacion": movimiento.observacion,
    }


@app.post("/api/v1/declaraciones/{id_residuo}/estado")
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
            "movimiento": _serializar_movimiento(movimiento),
        },
    )


@app.get("/api/v1/declaraciones/{id_residuo}/kardex")
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
            "movimientos": [_serializar_movimiento(m) for m in movimientos],
        },
    )

@app.post("/api/v1/acopio/verificar")
def verificar_acopio(grupos: List[str], db: Session = Depends(get_db)):
    """
    Evalúa incompatibilidad entre residuos en el punto de acopio.

    La matriz se lee de la tabla `reglas_incompatibilidad`, que es la fuente de
    verdad persistida; el módulo del clasificador solo la siembra.
    """
    try:
        veredicto = evaluar_compatibilidad(db, grupos)
        mensajes = {
            "NUNCA": "Incompatibilidad grave detectada. No juntar residuos.",
            "SEGREGAR": "Residuos requieren segregación en distintas bandejas.",
            "COMPATIBLE": "Residuos compatibles en el mismo punto de acopio.",
        }
        return success_response(
            message=mensajes[veredicto["veredicto"]],
            data=veredicto,
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_response(
                message="Error al verificar compatibilidad de acopio",
                error=str(e)
            )
        )

@app.get("/api/v1/historico/benchmark")
def diagnostico_historico():
    """
    Procesa y reclasifica los 856 residuos reales de DB_DeclaraciónResiduosPeligrosos.xlsx.
    """
    excel_path = os.getenv("HISTORICAL_EXCEL_PATH")
    if not excel_path:
        raise HTTPException(
            status_code=503,
            detail="HISTORICAL_EXCEL_PATH no está configurado para el benchmark histórico",
        )
    if not os.path.exists(excel_path):
        raise HTTPException(status_code=404, detail="Archivo DB_DeclaraciónResiduosPeligrosos.xlsx no encontrado")

    reporte = parsear_base_historica(excel_path)
    return success_response(
        message="Diagnóstico y reclasificación de la base histórica de 856 residuos completado",
        data=reporte
    )

if __name__ == "__main__":
    import uvicorn
    environment = os.getenv("APP_ENV", "development").lower()
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=environment == "development",
    )
