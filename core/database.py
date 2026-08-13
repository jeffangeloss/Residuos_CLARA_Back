"""
Configuración de Conexión a Base de Datos PostgreSQL / SQLAlchemy
CLARA+ Residuos Peligrosos - Universidad de Lima
"""

import os
from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# PostgreSQL es la base oficial. SQLite solo se usa explícitamente en desarrollo
# cuando no se ha definido DATABASE_URL; nunca hay fallback silencioso en staging
# o producción.
APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    if APP_ENV in {"production", "staging"}:
        raise RuntimeError("DATABASE_URL es obligatorio en staging y producción")
    DATABASE_URL = "sqlite:///./residuos_clara.db"
    print("⚠️ Desarrollo local: usando SQLite explícitamente. Configure DATABASE_URL para PostgreSQL.")

ES_SQLITE = DATABASE_URL.startswith("sqlite")

if ES_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _activar_claves_foraneas(conexion_dbapi, _registro):
        """SQLite ignora las claves foráneas salvo que se activen por conexión.

        Sin este PRAGMA las cláusulas ON DELETE CASCADE del esquema no se
        aplican en desarrollo y el comportamiento diverge de PostgreSQL.
        """
        cursor = conexion_dbapi.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )
    print("✅ Configurado PostgreSQL como base de datos oficial.")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Nombres deterministas para índices y restricciones. Sin esta convención cada
# motor inventa sus propios nombres y las migraciones de Alembic dejan de ser
# reproducibles entre SQLite y PostgreSQL.
CONVENCION_NOMBRES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Base = declarative_base(metadata=MetaData(naming_convention=CONVENCION_NOMBRES))

def get_db():
    """Dependency para Inyección de Sesión DB en FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
