"""Siembra y reconcilia los datos maestros de CLARA+.

Se ejecuta después de aplicar las migraciones:

    venv/bin/alembic upgrade head
    venv/bin/python seed.py

Es idempotente: volver a ejecutarlo tras corregir la ontología o la matriz de
incompatibilidad deja la base sincronizada sin tocar las declaraciones.
"""

import sys

from core.database import SessionLocal, DATABASE_URL
from core.seeder_3fn import sembrar_datos_maestros


def main() -> int:
    motor = "SQLite (desarrollo)" if DATABASE_URL.startswith("sqlite") else "PostgreSQL"
    print(f"Sembrando datos maestros en {motor}...")

    db = SessionLocal()
    try:
        resumen = sembrar_datos_maestros(db)
    finally:
        db.close()

    # Una categoría obsoleta con declaraciones asociadas no se puede retirar sin
    # una decisión del responsable de dominio: se reporta como salida distinta
    # de cero para que no pase inadvertida en un despliegue.
    return 1 if resumen["categorias_huerfanas_retenidas"] else 0


if __name__ == "__main__":
    sys.exit(main())
