"""Almacenamiento de las fotografías de envase.

La página 2 del formato oficial de declaración es una tabla de fotos de envase
con sus dimensiones. Hasta ahora `foto_url` se persistía pero la web enviaba
`"placeholder-url"`: no había ningún archivo detrás.

**Dónde viven las fotos es una decisión pendiente del CSBQR** (disco del
servidor, almacenamiento de objetos, o el Drive institucional que ya usan).
Este módulo implementa la opción reversible: disco local, en la ruta que indique
`ALMACENAMIENTO_FOTOS`. Todo el resto del sistema referencia las fotos por su
URL `/api/v1/fotos/<nombre>`, así que mudar el almacén a S3 o a Drive es
reescribir este archivo, no perseguir rutas por el código.

El nombre del archivo lo genera el servidor y nunca el cliente: un nombre que
llega de fuera puede contener `../` y escribir donde no debe.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import Tuple
from uuid import uuid4

# Formatos que el formato oficial admite incrustar. No se acepta nada más: un
# archivo arbitrario servido de vuelta al navegador es una vía de ataque, y
# aquí solo hacen falta fotos.
TIPOS_ADMITIDOS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}

# Un envase fotografiado con un móvil actual ronda los 3 MB. El tope deja
# margen para eso sin permitir que una subida llene el disco.
TAMANO_MAXIMO_BYTES = 12 * 1024 * 1024

# Solo lo que este módulo genera: fecha, identificador y extensión conocida.
_NOMBRE_VALIDO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{32}\.(jpg|png|webp|heic)$")


class FotoRechazada(ValueError):
    """La imagen no cumple tipo o tamaño y no se guarda."""


def directorio_fotos() -> Path:
    """Carpeta donde se guardan las fotos, creándola si hace falta."""
    ruta = Path(os.getenv("ALMACENAMIENTO_FOTOS", "almacenamiento/fotos"))
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _extension(tipo_declarado: str, nombre_original: str) -> str:
    """Extensión a partir del tipo declarado, con el nombre como respaldo."""
    tipo = (tipo_declarado or "").split(";")[0].strip().lower()
    if tipo in TIPOS_ADMITIDOS:
        return TIPOS_ADMITIDOS[tipo]

    sufijo = Path(unicodedata.normalize("NFKD", nombre_original or "")).suffix.lower()
    if sufijo in {".jpeg", ".jpg"}:
        return ".jpg"
    if sufijo in {".png", ".webp", ".heic"}:
        return sufijo

    raise FotoRechazada(
        f"Formato de imagen no admitido: '{tipo_declarado or nombre_original}'. "
        f"Admitidos: {', '.join(sorted(TIPOS_ADMITIDOS))}."
    )


def guardar_foto(contenido: bytes, tipo_declarado: str, nombre_original: str) -> Tuple[str, str]:
    """Guarda una imagen y devuelve su nombre de archivo y la URL para leerla.

    El nombre lo compone el servidor: un prefijo corto para poder agrupar por
    lote y un identificador aleatorio. El nombre que envía el cliente solo se
    consulta para deducir la extensión, nunca para nombrar el archivo.
    """
    if not contenido:
        raise FotoRechazada("La imagen llegó vacía")
    if len(contenido) > TAMANO_MAXIMO_BYTES:
        megas = len(contenido) / (1024 * 1024)
        raise FotoRechazada(
            f"La imagen pesa {megas:.1f} MB y el máximo es "
            f"{TAMANO_MAXIMO_BYTES // (1024 * 1024)} MB"
        )

    extension = _extension(tipo_declarado, nombre_original)
    identificador = uuid4().hex
    nombre = f"{identificador[:8]}-{identificador}{extension}"

    destino = directorio_fotos() / nombre
    destino.write_bytes(contenido)
    return nombre, f"/api/v1/fotos/{nombre}"


def ruta_de_foto(nombre: str) -> Path:
    """Ruta en disco de una foto ya guardada.

    Valida el nombre contra el patrón que genera este módulo antes de tocar el
    sistema de archivos: sin esa comprobación, un nombre como `../../.env`
    serviría cualquier archivo del servidor.
    """
    if not _NOMBRE_VALIDO.match(nombre or ""):
        raise FotoRechazada(f"Nombre de foto no válido: '{nombre}'")

    directorio = directorio_fotos().resolve()
    destino = (directorio / nombre).resolve()
    if destino.parent != directorio:
        raise FotoRechazada(f"Nombre de foto no válido: '{nombre}'")
    return destino
