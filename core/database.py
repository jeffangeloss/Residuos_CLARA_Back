"""
Conexión a PostgreSQL con SQLAlchemy
CLARA+ Residuos Peligrosos - Universidad de Lima

**PostgreSQL es el único motor admitido.** Hasta la Fase 9 el proyecto también
corría sobre SQLite en desarrollo, y esa comodidad tenía un precio: SQLite es
permisivo donde PostgreSQL no lo es —no aplica el largo de los `VARCHAR`, no
respeta las claves foráneas si no se le pide por conexión, y pliega mayúsculas
solo en ASCII—, así que un error podía pasar desapercibido en local y aparecer
al desplegar. En una declaración regulatoria de residuos peligrosos eso no
compensa. Decisión del 2026-08-13.
"""

import os

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import core.entorno  # noqa: F401  Carga el .env antes de leer nada del entorno.

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL es obligatorio. CLARA+ funciona únicamente sobre "
        "PostgreSQL; no hay base de respaldo en disco.\n\n"
        "  export DATABASE_URL="
        "'postgresql+psycopg2://usuario@localhost/residuos_clara_dev'\n\n"
        "O defínalo en el archivo .env del backend (vea .env.example)."
    )

if DATABASE_URL.startswith("sqlite"):
    raise RuntimeError(
        "SQLite ya no está admitido. Es permisivo donde PostgreSQL no lo es "
        "—largo de los campos, claves foráneas y plegado de acentos—, y una "
        "declaración validada solo contra SQLite no está validada.\n\n"
        "Indique una URL de PostgreSQL en DATABASE_URL."
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Nombres deterministas para índices y restricciones. Sin esta convención, cada
# migración inventa sus propios nombres y dejan de ser reproducibles: una
# restricción creada hoy no se puede eliminar mañana porque nadie sabe cómo se
# llama.
CONVENCION_NOMBRES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=CONVENCION_NOMBRES))


def get_db():
    """Sesión de base de datos para inyectar en las rutas de FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
