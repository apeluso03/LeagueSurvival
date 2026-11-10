"""discord bot

Revision ID: b5e0c3f19a72
Revises: f8b2d4c6a9e1
Create Date: 2026-11-10 12:00:00.000000

The Discord bot (SPEC 19): a Discord id on accounts, the server each group linked, the bot's
messages (to edit them later) and the event outbox the bot sends from.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models import UTCDateTime


revision: str = 'b5e0c3f19a72'
down_revision: Union[str, Sequence[str], None] = 'f8b2d4c6a9e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tolerates a partial earlier run (SQLite DDL isn't transactional).
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    if 'discord_id' not in {c['name'] for c in inspector.get_columns('user')}:
        with op.batch_alter_table('user', schema=None) as batch:
            batch.add_column(sa.Column('discord_id', sa.String(), nullable=True))
            batch.create_index('ix_user_discord_id', ['discord_id'], unique=True)

    if 'discordlink' not in tables:
        op.create_table(
            'discordlink',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('group.id'), nullable=False, unique=True),
            sa.Column('guild_id', sa.String(), nullable=False),
            sa.Column('guild_name', sa.String(), nullable=False, server_default=''),
            sa.Column('channel_id', sa.String(), nullable=True),
            sa.Column('installed_by_user_id', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
            sa.Column('muted', sa.JSON(), nullable=False),
            sa.Column('announced', sa.JSON(), nullable=False),
            sa.Column('state', sa.JSON(), nullable=False),
            sa.Column('last_error', sa.String(), nullable=True),
            sa.Column('created_at', UTCDateTime(), nullable=False),
        )
        op.create_index('ix_discordlink_guild_id', 'discordlink', ['guild_id'], unique=True)

    if 'discordmessage' not in tables:
        op.create_table(
            'discordmessage',
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('group.id'), primary_key=True),
            sa.Column('kind', sa.String(), primary_key=True),
            sa.Column('ref_id', sa.Integer(), primary_key=True),
            sa.Column('channel_id', sa.String(), nullable=False),
            sa.Column('message_id', sa.String(), nullable=False),
            sa.Column('data', sa.JSON(), nullable=False),
            sa.Column('updated_at', UTCDateTime(), nullable=False),
        )

    if 'eventoutbox' not in tables:
        op.create_table(
            'eventoutbox',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('group_id', sa.Integer(), sa.ForeignKey('group.id'), nullable=False),
            sa.Column('type', sa.String(), nullable=False),
            sa.Column('payload', sa.JSON(), nullable=False),
            sa.Column('created_at', UTCDateTime(), nullable=False),
            sa.Column('sent_at', UTCDateTime(), nullable=True),
            sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('error', sa.String(), nullable=True),
        )
        op.create_index('ix_eventoutbox_group_id', 'eventoutbox', ['group_id'])


def downgrade() -> None:
    op.drop_index('ix_eventoutbox_group_id', table_name='eventoutbox')
    op.drop_table('eventoutbox')
    op.drop_table('discordmessage')
    op.drop_index('ix_discordlink_guild_id', table_name='discordlink')
    op.drop_table('discordlink')
    with op.batch_alter_table('user', schema=None) as batch:
        batch.drop_index('ix_user_discord_id')
        batch.drop_column('discord_id')
