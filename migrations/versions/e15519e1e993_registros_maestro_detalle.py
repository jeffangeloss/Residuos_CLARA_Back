"""registros maestro detalle

Introduce la cabecera de visita (`registros`) y cuelga las declaraciones de
ella, reproduciendo la estructura real del proceso: se visita un laboratorio
una vez y se declaran allí varios envases.

Las declaraciones que ya existan se agrupan por laboratorio, responsable y
fecha, que es el criterio con el que el proceso real separa una visita de otra.
El traspaso se hace antes de volver obligatoria la clave foránea y antes de
retirar las columnas que se mueven, de modo que ningún dato quede sin destino.

Revision ID: e15519e1e993
Revises: 206f511ee1f3
Create Date: 2026-08-13

"""
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e15519e1e993'
down_revision: Union[str, Sequence[str], None] = '206f511ee1f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sufijo(nombre: str) -> str:
    """Cuatro letras derivadas del nombre, como en los códigos históricos."""
    import unicodedata

    limpio = "".join(
        c for c in unicodedata.normalize("NFD", nombre or "")
        if unicodedata.category(c) != "Mn"
    )
    palabras = [p for p in limpio.upper().split() if p.isalpha()]
    if not palabras:
        return "XXXX"
    iniciales = "".join(p[0] for p in palabras)[:4]
    if len(iniciales) == 4:
        return iniciales
    return (iniciales[:-1] + palabras[-1] + "XXXX")[:4]


def _traspasar_declaraciones_a_registros(conexion) -> None:
    """Crea un registro por cada grupo (laboratorio, responsable, fecha)."""
    filas = conexion.execute(sa.text("""
        SELECT id, laboratorio_id, responsable, elaborado_por, fecha
        FROM declaraciones
        ORDER BY fecha, id
    """)).fetchall()

    if not filas:
        return

    registros_por_clave = {}
    secuencia_por_fecha = {}
    # Marca temporal calculada en Python: `sa.func.now()` no es un valor y no
    # puede viajar como parámetro enlazado.
    ahora = datetime.now(timezone.utc)

    for fila in filas:
        clave = (fila.laboratorio_id, (fila.responsable or "").strip().casefold(), fila.fecha)
        if clave not in registros_por_clave:
            fecha = fila.fecha
            token = fecha.strftime("%d%m%Y") if hasattr(fecha, "strftime") else str(fecha)
            secuencia = secuencia_por_fecha.get(token, 0)
            secuencia_por_fecha[token] = secuencia + 1
            codigo = f"{token}{secuencia:06d}-{_sufijo(fila.responsable)}"

            conexion.execute(
                sa.text("""
                    INSERT INTO registros
                        (codigo, laboratorio_id, responsable_encargado, elaborado_por,
                         fecha, creado_en, actualizado_en)
                    VALUES
                        (:codigo, :laboratorio_id, :responsable, :elaborado_por,
                         :fecha, :ahora, :ahora)
                """),
                {
                    "codigo": codigo,
                    "laboratorio_id": fila.laboratorio_id,
                    "responsable": fila.responsable,
                    "elaborado_por": fila.elaborado_por,
                    "fecha": fila.fecha,
                    "ahora": ahora,
                },
            )
            registros_por_clave[clave] = conexion.execute(
                sa.text("SELECT id FROM registros WHERE codigo = :codigo"), {"codigo": codigo}
            ).scalar()

        conexion.execute(
            sa.text("UPDATE declaraciones SET registro_id = :rid WHERE id = :did"),
            {"rid": registros_por_clave[clave], "did": fila.id},
        )


def upgrade() -> None:
    op.create_table(
        'registros',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('codigo', sa.String(length=40), nullable=False),
        sa.Column('laboratorio_id', sa.Integer(), nullable=False),
        sa.Column('responsable_encargado', sa.String(length=150), nullable=False),
        sa.Column('elaborado_por', sa.String(length=150), nullable=True),
        sa.Column('fecha', sa.Date(), nullable=False),
        sa.Column('telefono_contacto', sa.String(length=30), nullable=True),
        sa.Column('comentarios_generales', sa.Text(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), nullable=False),
        sa.Column('actualizado_en', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['laboratorio_id'], ['laboratorios.id'],
                                name=op.f('fk_registros_laboratorio_id_laboratorios')),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'],
                                name=op.f('fk_registros_usuario_id_usuarios')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_registros')),
    )
    with op.batch_alter_table('registros', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_registros_codigo'), ['codigo'], unique=True)
        batch_op.create_index(batch_op.f('ix_registros_fecha'), ['fecha'], unique=False)
        batch_op.create_index(batch_op.f('ix_registros_id'), ['id'], unique=False)
        batch_op.create_index(batch_op.f('ix_registros_laboratorio_id'), ['laboratorio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_registros_usuario_id'), ['usuario_id'], unique=False)

    # Columnas nuevas admitiendo nulos, para poder rellenarlas con los datos ya
    # existentes antes de exigirlas.
    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('registro_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('codigo_formato', sa.String(length=40), nullable=True))

    _traspasar_declaraciones_a_registros(op.get_bind())

    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.alter_column('registro_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('responsable', existing_type=sa.String(length=100),
                              type_=sa.String(length=150), existing_nullable=False)
        batch_op.create_index(batch_op.f('ix_declaraciones_registro_id'), ['registro_id'], unique=False)
        batch_op.create_unique_constraint(
            op.f('uq_declaraciones_registro_id_codigo_formato'),
            ['registro_id', 'codigo_formato'],
        )
        batch_op.create_foreign_key(
            op.f('fk_declaraciones_registro_id_registros'), 'registros',
            ['registro_id'], ['id'], ondelete='CASCADE',
        )
        # El laboratorio y el "elaborado por" pasan a vivir en la cabecera.
        batch_op.drop_index(batch_op.f('ix_declaraciones_laboratorio_id'))
        batch_op.drop_constraint(op.f('fk_declaraciones_laboratorio_id_laboratorios'),
                                 type_='foreignkey')
        batch_op.drop_column('laboratorio_id')
        batch_op.drop_column('elaborado_por')


def downgrade() -> None:
    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('laboratorio_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('elaborado_por', sa.String(length=100), nullable=True))

    conexion = op.get_bind()
    conexion.execute(sa.text("""
        UPDATE declaraciones
        SET laboratorio_id = (
            SELECT r.laboratorio_id FROM registros r WHERE r.id = declaraciones.registro_id
        ),
        elaborado_por = (
            SELECT r.elaborado_por FROM registros r WHERE r.id = declaraciones.registro_id
        )
    """))

    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.alter_column('laboratorio_id', existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column('responsable', existing_type=sa.String(length=150),
                              type_=sa.String(length=100), existing_nullable=False)
        batch_op.create_foreign_key(
            op.f('fk_declaraciones_laboratorio_id_laboratorios'), 'laboratorios',
            ['laboratorio_id'], ['id'],
        )
        batch_op.create_index(batch_op.f('ix_declaraciones_laboratorio_id'),
                              ['laboratorio_id'], unique=False)
        batch_op.drop_constraint(op.f('fk_declaraciones_registro_id_registros'), type_='foreignkey')
        batch_op.drop_constraint(op.f('uq_declaraciones_registro_id_codigo_formato'), type_='unique')
        batch_op.drop_index(batch_op.f('ix_declaraciones_registro_id'))
        batch_op.drop_column('codigo_formato')
        batch_op.drop_column('registro_id')

    with op.batch_alter_table('registros', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_registros_usuario_id'))
        batch_op.drop_index(batch_op.f('ix_registros_laboratorio_id'))
        batch_op.drop_index(batch_op.f('ix_registros_id'))
        batch_op.drop_index(batch_op.f('ix_registros_fecha'))
        batch_op.drop_index(batch_op.f('ix_registros_codigo'))

    op.drop_table('registros')
