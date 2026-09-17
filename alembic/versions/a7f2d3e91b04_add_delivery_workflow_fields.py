"""add_delivery_workflow_fields

Revision ID: a7f2d3e91b04
Revises: 46b5c1f945e4
Create Date: 2026-09-17 21:23:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7f2d3e91b04'
down_revision: Union[str, Sequence[str], None] = '46b5c1f945e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('magazyn_dostawy', sa.Column('awizacja_ref', sa.String(100), nullable=True, comment='Nr WZ dostawcy / ASN'))
    op.add_column('magazyn_dostawy', sa.Column('awizacja_by', sa.String(50), nullable=True))
    op.add_column('magazyn_dostawy', sa.Column('awizacja_at', sa.DateTime, nullable=True))
    op.add_column('magazyn_dostawy', sa.Column('strefa_przyjec', sa.String(50), server_default='STREFA_PRZYJEC_01', nullable=True))
    op.add_column('magazyn_dostawy', sa.Column('putaway_algorithm', sa.String(30), server_default='MANUAL', nullable=True, comment='MANUAL|ABC_ROTATION|NEAREST_EMPTY'))


def downgrade() -> None:
    op.drop_column('magazyn_dostawy', 'putaway_algorithm')
    op.drop_column('magazyn_dostawy', 'strefa_przyjec')
    op.drop_column('magazyn_dostawy', 'awizacja_at')
    op.drop_column('magazyn_dostawy', 'awizacja_by')
    op.drop_column('magazyn_dostawy', 'awizacja_ref')
