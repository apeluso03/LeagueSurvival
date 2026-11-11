"""daily statline

Revision ID: c7d2f4a8e1b3
Revises: b5e0c3f19a72
Create Date: 2026-11-11 12:00:00.000000

The daily guessing game (SPEC 20): one puzzle per group per day, built from a player's statline in
a past challenge game (never the same statline twice), and each person's guesses.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import UTCDateTime


revision: str = 'c7d2f4a8e1b3'
down_revision: Union[str, Sequence[str], None] = 'b5e0c3f19a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tolerates a partial earlier run (SQLite DDL isn't transactional).
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'dailypuzzle' not in tables:
        op.create_table(
            'dailypuzzle',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('group.id'), nullable=False),
            sa.Column('day', sa.String(), nullable=False),
            sa.Column('number', sa.Integer(), nullable=False),
            sa.Column('match_id', sa.String(), nullable=False),
            sa.Column('player_id', sa.Integer(), sa.ForeignKey('player.id'), nullable=False),
            sa.Column('game_id', sa.Integer(), sa.ForeignKey('challengegame.id'), nullable=False),
            sa.Column('created_at', UTCDateTime(), nullable=False),
            sa.UniqueConstraint('group_id', 'day', name='uq_dailypuzzle_group_day'),
            sa.UniqueConstraint('group_id', 'match_id', 'player_id', name='uq_dailypuzzle_statline'),
        )
        op.create_index('ix_dailypuzzle_group_id', 'dailypuzzle', ['group_id'])
    if 'dailyplay' not in tables:
        op.create_table(
            'dailyplay',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('puzzle_id', sa.Integer(), sa.ForeignKey('dailypuzzle.id'), nullable=False),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
            sa.Column('guesses', sa.JSON(), nullable=False),
            sa.Column('done', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('score', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', UTCDateTime(), nullable=False),
            sa.Column('finished_at', UTCDateTime(), nullable=True),
            sa.UniqueConstraint('puzzle_id', 'user_id', name='uq_dailyplay_puzzle_user'),
        )
        op.create_index('ix_dailyplay_puzzle_id', 'dailyplay', ['puzzle_id'])


def downgrade() -> None:
    op.drop_index('ix_dailyplay_puzzle_id', table_name='dailyplay')
    op.drop_table('dailyplay')
    op.drop_index('ix_dailypuzzle_group_id', table_name='dailypuzzle')
    op.drop_table('dailypuzzle')
