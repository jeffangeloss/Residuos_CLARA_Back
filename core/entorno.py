"""Carga la configuración del archivo `.env` del backend.

Hasta la Fase 9 existía `.env.example` y el README pedía copiarlo a `.env`,
pero **nadie leía ese archivo**: `os.getenv` no lo carga solo. El resultado era
que la configuración parecía puesta y no lo estaba, y el servicio arrancaba con
los valores por omisión sin avisar. Ese fue el origen de que una comprobación
acabara escribiendo en la base equivocada.

Este módulo se importa antes que cualquier otro que lea variables de entorno.
Lo que ya esté definido en el entorno **manda** sobre el archivo, para que un
despliegue pueda imponer sus valores sin editar ficheros.
"""

from pathlib import Path

from dotenv import load_dotenv

RAIZ_BACKEND = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = RAIZ_BACKEND / ".env"

# `override=False`: las variables del entorno tienen prioridad sobre el archivo.
load_dotenv(ARCHIVO_ENV, override=False)
