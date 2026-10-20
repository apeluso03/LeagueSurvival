"""live game id bigint

Revision ID: d4a8c2e61f07
Revises: b7d3e1f05a92
Create Date: 2026-10-20 18:00:00.000000

Riot's game ids (5,663,596,874 and up) don't fit a 32-bit integer. SQLite never cared; Postgres
does, so livegame.riot_game_id becomes BIGINT.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4a8c2e61f07'
down_revision: Union[str, Sequence[str], None] = 'b7d3e1f05a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('livegame', schema=None) as batch:
        batch.alter_column('riot_game_id', existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('livegame', schema=None) as batch:
        batch.alter_column('riot_game_id', existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True)
