"""live games

Revision ID: 3e7a5c20d4f8
Revises: 8c4d2a91f0b3
Create Date: 2026-10-17 18:00:00.000000

Safe to run again on a database where an earlier attempt stopped halfway: the table is only
created when it isn't there yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '3e7a5c20d4f8'
down_revision: Union[str, Sequence[str], None] = '8c4d2a91f0b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    if 'livegame' in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table('livegame',
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('riot_game_id', sa.Integer(), nullable=True),
    sa.Column('platform', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('queue_id', sa.Integer(), nullable=True),
    sa.Column('started_at', app.models.UTCDateTime(), nullable=True),
    sa.Column('detected_at', app.models.UTCDateTime(), nullable=False),
    sa.Column('checked_at', app.models.UTCDateTime(), nullable=True),
    sa.Column('updated_at', app.models.UTCDateTime(), nullable=True),
    sa.Column('ended_at', app.models.UTCDateTime(), nullable=True),
    sa.Column('our_team', sa.Integer(), nullable=True),
    sa.Column('participants', sa.JSON(), nullable=False),
    sa.Column('bans', sa.JSON(), nullable=False),
    sa.Column('state', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['game_id'], ['challengegame.id'], ),
    sa.PrimaryKeyConstraint('game_id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('livegame')
