"""accounts, sessions and invites

Revision ID: 5b1f0c7d9e21
Revises: e228ed9fca48
Create Date: 2026-10-16 12:00:00.000000

Safe to run again on a database where an earlier attempt stopped halfway: SQLite can't roll back
CREATE TABLE, so each table, index and column is only added when it isn't there yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = '5b1f0c7d9e21'
down_revision: Union[str, Sequence[str], None] = 'e228ed9fca48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    return {i['name'] for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    """Upgrade schema."""
    existing = _tables()
    if 'user' not in existing:
        op.create_table('user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('password_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('created_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('last_login_at', app.models.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('player_id')
        )
    if 'ix_user_username' not in _indexes('user'):
        with op.batch_alter_table('user', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_user_username'), ['username'], unique=True)

    if 'authsession' not in existing:
        op.create_table('authsession',
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('expires_at', app.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('token_hash')
        )
    if 'ix_authsession_user_id' not in _indexes('authsession'):
        with op.batch_alter_table('authsession', schema=None) as batch_op:
            batch_op.create_index(batch_op.f('ix_authsession_user_id'), ['user_id'], unique=False)

    if 'invite' not in existing:
        op.create_table('invite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('expires_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('used_at', app.models.UTCDateTime(), nullable=True),
        sa.Column('used_by_user_id', sa.Integer(), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    have = _indexes('invite')
    with op.batch_alter_table('invite', schema=None) as batch_op:
        if 'ix_invite_player_id' not in have:
            batch_op.create_index(batch_op.f('ix_invite_player_id'), ['player_id'], unique=False)
        if 'ix_invite_token_hash' not in have:
            batch_op.create_index(batch_op.f('ix_invite_token_hash'), ['token_hash'], unique=True)

    if 'owner_user_id' not in _columns('run'):
        with op.batch_alter_table('run', schema=None) as batch_op:
            batch_op.add_column(sa.Column('owner_user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_run_owner_user_id_user', 'user', ['owner_user_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('run', schema=None) as batch_op:
        batch_op.drop_constraint('fk_run_owner_user_id_user', type_='foreignkey')
        batch_op.drop_column('owner_user_id')
    with op.batch_alter_table('invite', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_invite_token_hash'))
        batch_op.drop_index(batch_op.f('ix_invite_player_id'))
    op.drop_table('invite')
    with op.batch_alter_table('authsession', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_authsession_user_id'))
    op.drop_table('authsession')
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_username'))
    op.drop_table('user')
