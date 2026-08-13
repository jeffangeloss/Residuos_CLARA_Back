"""Entorno de migraciones de Alembic para CLARA+.

La URL de conexión no se escribe en `alembic.ini`: se toma de `core.database`,
que a su vez lee `DATABASE_URL` y aplica la regla de que PostgreSQL es
obligatorio en staging y producción. Así la migración y la aplicación no pueden
apuntar a bases distintas.
"""

from logging.config import fileConfig
import os
import sys

from alembic import context

# Permite importar `core.*` cuando Alembic se ejecuta desde la raíz del backend.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Base, engine  # noqa: E402
import core.db_models  # noqa: F401,E402  (registra las tablas en Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL de la migración sin conectarse a la base."""
    context.configure(
        url=str(engine.url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base configurada."""
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # SQLite no soporta ALTER TABLE para la mayoría de cambios; el modo
            # batch recrea la tabla y mantiene las migraciones aplicables tanto
            # en desarrollo local como en PostgreSQL.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
