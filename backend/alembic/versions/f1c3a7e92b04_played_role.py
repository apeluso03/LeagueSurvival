"""played role

Revision ID: f1c3a7e92b04
Revises: d4a8c2e61f07
Create Date: 2026-10-22 12:00:00.000000

The role a player says they're actually in (autofilled, swapped lanes), so builds follow it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1c3a7e92b04'
down_revision: Union[str, Sequence[str], None] = 'd4a8c2e61f07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tolerates a partial earlier run (SQLite DDL isn't transactional).
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('spinassignment')}
    if 'played_role' not in columns:
        with op.batch_alter_table('spinassignment', schema=None) as batch:
            batch.add_column(sa.Column('played_role', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('spinassignment', schema=None) as batch:
        batch.drop_column('played_role')
