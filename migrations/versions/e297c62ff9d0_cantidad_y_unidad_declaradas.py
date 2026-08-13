"""cantidad y unidad declaradas

La cifra que imprime el formato oficial es `Cantidad` con su `Unidad`, y el
formato acepta tanto kilogramos como litros: 277 de los 856 registros históricos
están en litros y con el modelo anterior, que solo conocía gramos, no se podían
representar.

El pesaje pasa a ser evidencia opcional en lugar de la única forma de indicar
cuánto residuo hay. Las declaraciones que ya existen se convierten a cantidad en
kilogramos con modo de medición "pesaje", que es lo que eran.

Revision ID: e297c62ff9d0
Revises: c7891e12854f
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e297c62ff9d0'
down_revision: Union[str, Sequence[str], None] = 'c7891e12854f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Columnas nuevas admitiendo nulos, para poder rellenarlas.
    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cantidad', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('unidad', sa.String(length=4), nullable=True))
        batch_op.add_column(sa.Column('modo_medicion', sa.String(length=12), nullable=True))

    # 2. Lo ya declarado era siempre una masa pesada en balanza.
    op.execute("""
        UPDATE declaraciones
        SET cantidad = peso_neto_kg, unidad = 'Kg', modo_medicion = 'pesaje'
    """)

    # 3. Se exigen las columnas nuevas, se retira la antigua y el pesaje pasa a
    #    ser opcional. Las restricciones que mencionaban `peso_neto_kg` se
    #    reemplazan por las equivalentes sobre `cantidad`.
    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_neto_kg_no_negativo'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_neto_kg_coherente'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_bruto_no_negativo'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_tara_no_negativa'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_neto_no_negativo'), type_='check')

        batch_op.alter_column('cantidad', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('unidad', existing_type=sa.String(length=4), nullable=False)
        batch_op.alter_column('modo_medicion', existing_type=sa.String(length=12), nullable=False)
        batch_op.alter_column('peso_bruto_g', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('tara_g', existing_type=sa.Float(), nullable=True)
        batch_op.alter_column('peso_neto_g', existing_type=sa.Float(), nullable=True)
        batch_op.drop_column('peso_neto_kg')

        batch_op.create_check_constraint(
            'peso_bruto_no_negativo', 'peso_bruto_g IS NULL OR peso_bruto_g >= 0')
        batch_op.create_check_constraint(
            'tara_no_negativa', 'tara_g IS NULL OR tara_g >= 0')
        batch_op.create_check_constraint(
            'peso_neto_no_negativo', 'peso_neto_g IS NULL OR peso_neto_g >= 0')
        batch_op.create_check_constraint('cantidad_positiva', 'cantidad > 0')
        batch_op.create_check_constraint('unidad_valida', "unidad IN ('Kg', 'L')")
        batch_op.create_check_constraint(
            'modo_medicion_valido', "modo_medicion IN ('declarada', 'pesaje')")
        batch_op.create_check_constraint(
            'pesaje_con_evidencia',
            "modo_medicion <> 'pesaje' OR "
            "(peso_bruto_g IS NOT NULL AND peso_neto_g IS NOT NULL AND unidad = 'Kg')")
        batch_op.create_check_constraint(
            'cantidad_coherente_con_pesaje',
            "peso_neto_g IS NULL OR cantidad * 1000 BETWEEN peso_neto_g - 1 AND peso_neto_g + 1")

    # 4. Un residuo declarado por volumen no tiene masa que mover en el kardex.
    with op.batch_alter_table('movimientos_kardex', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_movimientos_kardex_cantidad_no_negativa'), type_='check')
        batch_op.alter_column('cantidad_g', existing_type=sa.Float(), nullable=True)
        batch_op.create_check_constraint(
            'cantidad_no_negativa', 'cantidad_g IS NULL OR cantidad_g >= 0')


def downgrade() -> None:
    # Solo se puede volver atrás lo que estaba en kilogramos: un residuo
    # declarado en litros no tiene equivalente en el modelo anterior.
    op.execute("DELETE FROM declaraciones WHERE unidad <> 'Kg'")

    with op.batch_alter_table('movimientos_kardex', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_movimientos_kardex_cantidad_no_negativa'), type_='check')
        batch_op.execute("UPDATE movimientos_kardex SET cantidad_g = 0 WHERE cantidad_g IS NULL")
        batch_op.alter_column('cantidad_g', existing_type=sa.Float(), nullable=False)
        batch_op.create_check_constraint('cantidad_no_negativa', 'cantidad_g >= 0')

    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('peso_neto_kg', sa.Float(), nullable=True))

    op.execute("UPDATE declaraciones SET peso_neto_kg = cantidad")
    op.execute("UPDATE declaraciones SET peso_bruto_g = 0 WHERE peso_bruto_g IS NULL")
    op.execute("UPDATE declaraciones SET tara_g = 0 WHERE tara_g IS NULL")
    op.execute("UPDATE declaraciones SET peso_neto_g = cantidad * 1000 WHERE peso_neto_g IS NULL")

    with op.batch_alter_table('declaraciones', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_declaraciones_cantidad_positiva'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_unidad_valida'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_modo_medicion_valido'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_pesaje_con_evidencia'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_cantidad_coherente_con_pesaje'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_bruto_no_negativo'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_tara_no_negativa'), type_='check')
        batch_op.drop_constraint(op.f('ck_declaraciones_peso_neto_no_negativo'), type_='check')

        batch_op.alter_column('peso_neto_kg', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('peso_bruto_g', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('tara_g', existing_type=sa.Float(), nullable=False)
        batch_op.alter_column('peso_neto_g', existing_type=sa.Float(), nullable=False)
        batch_op.drop_column('modo_medicion')
        batch_op.drop_column('unidad')
        batch_op.drop_column('cantidad')

        batch_op.create_check_constraint('peso_bruto_no_negativo', 'peso_bruto_g >= 0')
        batch_op.create_check_constraint('tara_no_negativa', 'tara_g >= 0')
        batch_op.create_check_constraint('peso_neto_no_negativo', 'peso_neto_g >= 0')
        batch_op.create_check_constraint('peso_neto_kg_no_negativo', 'peso_neto_kg >= 0')
        batch_op.create_check_constraint(
            'peso_neto_kg_coherente',
            'peso_neto_kg * 1000 BETWEEN peso_neto_g - 1 AND peso_neto_g + 1')
