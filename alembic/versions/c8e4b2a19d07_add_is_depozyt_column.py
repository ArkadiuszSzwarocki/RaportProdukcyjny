"""Add is_depozyt flag to delivery and warehouse stock tables.

Revision ID: c8e4b2a19d07
Revises: a7f2d3e91b04
Create Date: 2026-11-19 20:12:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'c8e4b2a19d07'
down_revision: Union[str, Sequence[str], None] = 'a7f2d3e91b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET_TABLES = (
    'magazyn_dostawy',
    'magazyn_surowce',
    'magazyn_agro_surowce',
    'magazyn_opakowania',
    'magazyn_agro_opakowania',
    'magazyn_dodatki',
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in _TARGET_TABLES:
        if table_name not in existing_tables:
            continue
        columns = {col['name'] for col in inspector.get_columns(table_name)}
        if 'is_depozyt' not in columns:
            op.add_column(
                table_name,
                sa.Column('is_depozyt', sa.Boolean(), nullable=False, server_default=sa.text('0')),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())
    for table_name in reversed(_TARGET_TABLES):
        if table_name not in existing_tables:
            continue
        columns = {col['name'] for col in inspector.get_columns(table_name)}
        if 'is_depozyt' in columns:
            op.drop_column(table_name, 'is_depozyt')
