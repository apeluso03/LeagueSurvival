"""meta crawler, player colors and titles

Revision ID: e228ed9fca48
Revises: a6dbfe6466fd
Create Date: 2026-10-15 19:03:30.361058

Safe to run again on a database where an earlier attempt stopped halfway: SQLite can't roll back
CREATE TABLE, so each table, index and column is only added when it isn't there yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = 'e228ed9fca48'
down_revision: Union[str, Sequence[str], None] = 'a6dbfe6466fd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def _add_missing(table: str, columns: list[sa.Column]) -> None:
    have = _columns(table)
    missing = [c for c in columns if c.name not in have]
    if missing:
        with op.batch_alter_table(table, schema=None) as batch_op:
            for column in missing:
                batch_op.add_column(column)


def upgrade() -> None:
    """Upgrade schema."""
    existing = _tables()
    if 'metachamprole' not in existing:
        op.create_table('metachamprole',
        sa.Column('champion_key', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('champion_key', 'role', 'patch')
        )
    if 'metacrawlstate' not in existing:
        op.create_table('metacrawlstate',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('puuids', sa.JSON(), nullable=False),
        sa.Column('next_index', sa.Integer(), nullable=False),
        sa.Column('refreshed_at', app.models.UTCDateTime(), nullable=True),
        sa.Column('last_run_at', app.models.UTCDateTime(), nullable=True),
        sa.Column('last_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('matches_counted', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    if 'metaitem' not in existing:
        op.create_table('metaitem',
        sa.Column('champion_key', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('item_id', sa.Integer(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('champion_key', 'role', 'patch', 'item_id')
        )
    if 'metamatch' not in existing:
        op.create_table('metamatch',
        sa.Column('match_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('counted_at', app.models.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint('match_id')
        )
    if 'ix_metamatch_patch' not in _indexes('metamatch'):
        with op.batch_alter_table('metamatch', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_metamatch_patch'), ['patch'], unique=False)
    if 'metarunepage' not in existing:
        op.create_table('metarunepage',
        sa.Column('champion_key', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('patch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('page', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('games', sa.Integer(), nullable=False),
        sa.Column('wins', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('champion_key', 'role', 'patch', 'page')
        )

    _add_missing('appsettings', [
        sa.Column('meta_crawl', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('meta_platform', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='na1'),
        sa.Column('meta_region', sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default='americas'),
    ])
    _add_missing('champion', [sa.Column('positions', sa.JSON(), nullable=False, server_default='[]')])
    _add_missing('player', [
        sa.Column('color', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    ])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('player', schema=None) as batch_op:
        batch_op.drop_column('title')
        batch_op.drop_column('color')

    with op.batch_alter_table('champion', schema=None) as batch_op:
        batch_op.drop_column('positions')

    with op.batch_alter_table('appsettings', schema=None) as batch_op:
        batch_op.drop_column('meta_region')
        batch_op.drop_column('meta_platform')
        batch_op.drop_column('meta_crawl')

    op.drop_table('metarunepage')
    with op.batch_alter_table('metamatch', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_metamatch_patch'))

    op.drop_table('metamatch')
    op.drop_table('metaitem')
    op.drop_table('metacrawlstate')
    op.drop_table('metachamprole')
