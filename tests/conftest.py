"""Configuración común de las pruebas de persistencia.

Cada prueba corre contra una base SQLite en archivo temporal, creada aplicando
las migraciones de Alembic —no `create_all`—, de modo que lo que se verifica es
exactamente el esquema que se desplegará.
"""

import os
import sys
import tempfile

import pytest

RAIZ_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ_BACKEND)


@pytest.fixture()
def url_base_temporal():
    """URL de una base vacía y aislada por prueba.

    Por defecto usa SQLite en archivo temporal. Definiendo
    `CLARA_TEST_DATABASE_URL` la misma suite corre contra PostgreSQL, que es la
    base oficial; así la paridad entre motores es verificable y no una
    comprobación puntual:

        CLARA_TEST_DATABASE_URL=postgresql+psycopg2://usuario@localhost/clara_test \\
            venv/bin/python -m pytest tests/
    """
    url_externa = os.getenv("CLARA_TEST_DATABASE_URL")
    if url_externa:
        yield url_externa
        return

    descriptor, ruta = tempfile.mkstemp(suffix=".db", prefix="clara_test_")
    os.close(descriptor)
    os.unlink(ruta)  # Alembic debe crear el archivo desde cero.
    try:
        yield f"sqlite:///{ruta}"
    finally:
        if os.path.exists(ruta):
            os.unlink(ruta)


@pytest.fixture()
def db(url_base_temporal, monkeypatch):
    """Sesión sobre una base migrada y con los datos maestros sembrados."""
    monkeypatch.setenv("DATABASE_URL", url_base_temporal)
    monkeypatch.setenv("APP_ENV", "development")

    # `core.database` resuelve la URL al importarse, así que los módulos que
    # dependen de ella deben recargarse contra la base de esta prueba.
    for modulo in [
        "core.repositorio", "core.seeder_3fn", "core.db_models", "core.database",
    ]:
        sys.modules.pop(modulo, None)

    from alembic import command
    from alembic.config import Config

    configuracion = Config(os.path.join(RAIZ_BACKEND, "alembic.ini"))
    configuracion.set_main_option("script_location", os.path.join(RAIZ_BACKEND, "migrations"))
    if os.getenv("CLARA_TEST_DATABASE_URL"):
        # Una base PostgreSQL se reutiliza entre pruebas: hay que vaciarla
        # aplicando el downgrade, que además ejercita la migración inversa.
        command.downgrade(configuracion, "base")
    command.upgrade(configuracion, "head")

    from core.database import SessionLocal
    from core.seeder_3fn import sembrar_datos_maestros

    sesion = SessionLocal()
    sembrar_datos_maestros(sesion, verboso=False)
    try:
        yield sesion
    finally:
        sesion.close()
