"""summoner spells and matchups

Revision ID: 8c4d2a91f0b3
Revises: 5b1f0c7d9e21
Create Date: 2026-10-17 12:00:00.000000

Safe to run again on a database where an earlier attempt stopped halfway: SQLite can't roll back
CREATE TABLE, so each table and column is only added when it isn't there yet. Matches counted
before this get metamatch.extras = false, and the crawler re-fetches them to fill in the new data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '8c4d2a91f0b3'
down_revision: Union[str, Sequence[str], None] = '5b1f0c7d9e21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Upgrade schema."""
    existing = _tables()
    if 'metaspells' not in existing:
        op.create_table('metaspells',
        sa.Column('champion_key', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('spells', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('champion_key', 'role', 'patch', 'spells')
        )
    if 'metamatchup' not in existing:
        op.create_table('metamatchup',
        sa.Column('champion_key', sa.Integer(), nullable=False),
        sa.Column('enemy_key', sa.Integer(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('champion_key', 'enemy_key', 'patch')
        )
    if 'extras' not in _columns('metamatch'):
        with op.batch_alter_table('metamatch', schema=None) as batch_op:
            batch_op.add_column(sa.Column('extras', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('metamatch', schema=None) as batch_op:
        batch_op.drop_column('extras')
    op.drop_table('metamatchup')
    op.drop_table('metaspells')
