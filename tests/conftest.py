"""Configuración común de las pruebas.

Cada prueba corre contra una base PostgreSQL desechable, creada aplicando las
migraciones de Alembic —no `create_all`—, de modo que lo que se verifica es
exactamente el esquema que se desplegará.

Hasta la Fase 9 la suite corría por defecto sobre SQLite en archivo temporal y
solo opcionalmente sobre PostgreSQL. Se retiró: SQLite no aplica el largo de los
`VARCHAR` ni respeta las claves foráneas sin activarlas por conexión, así que
una prueba verde allí no demostraba lo mismo que una prueba verde aquí.
"""

import os
import sys

import pytest

RAIZ_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ_BACKEND)

BASE_POR_DEFECTO = "residuos_clara_test"


def _url_de_pruebas() -> str:
    """URL de la base desechable, tomando el usuario del sistema si hace falta."""
    configurada = os.getenv("CLARA_TEST_DATABASE_URL")
    if configurada:
        return configurada

    usuario = os.getenv("PGUSER") or os.getenv("USER") or "postgres"
    return f"postgresql+psycopg2://{usuario}@localhost/{BASE_POR_DEFECTO}"


@pytest.fixture(scope="session")
def url_base_temporal():
    """Base PostgreSQL desechable para toda la sesión de pruebas.

    Se comprueba al principio que exista y sea alcanzable: un fallo de conexión
    a mitad de la suite se lee como cien pruebas rotas, y en realidad es una
    base que no está creada.
    """
    url = _url_de_pruebas()

    try:
        import psycopg2

        conexion = psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://"))
        conexion.close()
    except Exception as fallo:
        pytest.exit(
            f"No se pudo conectar a la base de pruebas.\n\n  {url}\n\n{fallo}\n"
            f"Cree la base con:\n\n  createdb {BASE_POR_DEFECTO}\n\n"
            "O indique otra en CLARA_TEST_DATABASE_URL.",
            returncode=1,
        )

    yield url


@pytest.fixture()
def db(url_base_temporal, monkeypatch):
    """Sesión sobre una base migrada y con los datos maestros sembrados.

    La base se vacía aplicando `downgrade base` antes de cada prueba, lo que de
    paso ejercita la migración inversa en cada ejecución.
    """
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
