"""Fotografías del envase.

La página 2 del formato oficial de declaración es una tabla de fotos de envase
con sus dimensiones. Es la ventaja estructural del móvil sobre el formulario:
la cámara ya está en la mano de quien declara.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from core.almacenamiento import FotoRechazada, guardar_foto, ruta_de_foto
from core.response import success_response

router = APIRouter(prefix="/api/v1/fotos", tags=["fotos"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def subir_foto(archivo: UploadFile = File(...)):
    """Recibe la foto del envase y devuelve la URL con la que referenciarla."""
    try:
        contenido = await archivo.read()
        nombre, url = guardar_foto(contenido, archivo.content_type, archivo.filename)
    except FotoRechazada as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return success_response(
        message="Fotografía almacenada",
        data={"nombre": nombre, "foto_url": url, "bytes": len(contenido)},
    )


@router.get("/{nombre}")
def obtener_foto(nombre: str):
    """Sirve una fotografía ya almacenada."""
    try:
        ruta = ruta_de_foto(nombre)
    except FotoRechazada as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not ruta.is_file():
        raise HTTPException(status_code=404, detail=f"Fotografía no encontrada: {nombre}")
    return FileResponse(ruta)
