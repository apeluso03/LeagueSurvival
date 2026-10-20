"""groups

Revision ID: b7d3e1f05a92
Revises: 9a1f6b3c7e52
Create Date: 2026-10-20 12:00:00.000000

Turns the single-group app into many groups (SPEC 12.4):
- new tables: group, groupmember, sitesettings, siteinvite
- player, run, invite and appsettings get a group_id; authsession remembers the group being viewed
- everything that exists moves into one group owned by the site admin (the first account)
- each account's player becomes a group membership (user.player_id goes away)
- the site-wide parts of appsettings (Riot sync status, build crawler) move to sitesettings

Written with SQLAlchemy tables, not raw SQL: "group" and "user" are reserved words in Postgres.
Safe to run again on SQLite after a partial run: every step checks first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401

import app.models  # noqa: F401


revision: str = 'b7d3e1f05a92'
down_revision: Union[str, Sequence[str], None] = '9a1f6b3c7e52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _insp():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_insp().get_table_names())


def _columns(table: str) -> set[str]:
    return {c['name'] for c in _insp().get_columns(table)}


def _add(table: str, column: sa.Column) -> None:
    if column.name not in _columns(table):
        with op.batch_alter_table(table, schema=None) as batch:
            batch.add_column(column)


def upgrade() -> None:
    existing = _tables()
    if 'group' not in existing:
        op.create_table('group',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('owner_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', app.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
    if 'groupmember' not in existing:
        op.create_table('groupmember',
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('joined_at', app.models.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['group.id'], ),
        sa.ForeignKeyConstraint(['player_id'], ['player.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('group_id', 'user_id'),
        sa.UniqueConstraint('player_id')
        )
    if 'sitesettings' not in existing:
        op.create_table('sitesettings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('open_signup', sa.Boolean(), nullable=False),
        sa.Column('last_sync_at', app.models.UTCDateTime(), nullable=True),
        sa.Column('last_sync_error', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('meta_crawl', sa.Boolean(), nullable=False),
        sa.Column('meta_platform', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('meta_region', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
    if 'siteinvite' not in existing:
        op.create_table('siteinvite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('note', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('expires_at', app.models.UTCDateTime(), nullable=False),
        sa.Column('used_at', app.models.UTCDateTime(), nullable=True),
        sa.Column('used_by_user_id', sa.Integer(), nullable=True),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ),
        sa.ForeignKeyConstraint(['used_by_user_id'], ['user.id'], ),
        sa.PrimaryKeyConstraint('id')
        )
        with op.batch_alter_table('siteinvite', schema=None) as batch:
            batch.create_index(batch.f('ix_siteinvite_token_hash'), ['token_hash'], unique=True)

    # New group_id columns, nullable until they're filled in.
    for table in ('player', 'run', 'invite', 'appsettings', 'authsession'):
        _add(table, sa.Column('group_id', sa.Integer(), nullable=True))

    # --- move everything into one group ---------------------------------------------------
    bind = op.get_bind()
    md = sa.MetaData()
    user = sa.Table('user', md, autoload_with=bind)
    group = sa.Table('group', md, autoload_with=bind)
    member = sa.Table('groupmember', md, autoload_with=bind)
    site = sa.Table('sitesettings', md, autoload_with=bind)
    appsettings = sa.Table('appsettings', md, autoload_with=bind)
    tables = {t: sa.Table(t, md, autoload_with=bind) for t in ('player', 'run', 'invite', 'authsession')}

    from app.models import utcnow

    has_data = any(bind.execute(sa.select(sa.func.count()).select_from(tables[t])).scalar() for t in ('player', 'run')) or bind.execute(
        sa.select(sa.func.count()).select_from(user)
    ).scalar()
    group_id = bind.execute(sa.select(group.c.id).order_by(group.c.id)).scalar()
    if has_data and group_id is None:
        admin = bind.execute(sa.select(user.c.id, user.c.username).order_by(sa.desc(user.c.is_admin), user.c.id)).first()
        name = f"{admin.username}'s group" if admin else 'My group'
        group_id = bind.execute(
            group.insert().values(name=name, owner_user_id=admin.id if admin else None, created_at=utcnow()).returning(group.c.id)
        ).scalar()
    if group_id is not None:
        for t in ('player', 'run', 'invite', 'authsession'):
            bind.execute(tables[t].update().where(tables[t].c.group_id.is_(None)).values(group_id=group_id))
        first = bind.execute(sa.select(appsettings).order_by(appsettings.c.id)).first()
        if first is not None and first.group_id is None:
            bind.execute(appsettings.update().where(appsettings.c.id == first.id).values(group_id=group_id))
        bind.execute(appsettings.delete().where(appsettings.c.group_id.is_(None)))
        owner_id = bind.execute(sa.select(group.c.owner_user_id).where(group.c.id == group_id)).scalar()
        if 'player_id' in user.c:
            for u in bind.execute(sa.select(user.c.id, user.c.player_id)).all():
                if bind.execute(sa.select(member.c.user_id).where(member.c.group_id == group_id, member.c.user_id == u.id)).first():
                    continue
                bind.execute(member.insert().values(
                    group_id=group_id, user_id=u.id, role='owner' if u.id == owner_id else 'member',
                    player_id=u.player_id, joined_at=utcnow(),
                ))

    # Site-wide settings from the old single settings row.
    if bind.execute(sa.select(sa.func.count()).select_from(site)).scalar() == 0:
        old = bind.execute(sa.select(appsettings).order_by(appsettings.c.id)).first()
        values = dict(id=1, open_signup=False, meta_crawl=True, meta_platform='na1', meta_region='americas')
        if old is not None:
            for k in ('last_sync_at', 'last_sync_error', 'meta_crawl', 'meta_platform', 'meta_region'):
                if k in appsettings.c:
                    values[k] = getattr(old, k)
        bind.execute(site.insert().values(**values))

    # --- tighten: required group ids, drop what moved ---------------------------------------
    for table, unique in (('player', False), ('run', False), ('invite', False), ('appsettings', True)):
        with op.batch_alter_table(table, schema=None) as batch:
            batch.alter_column('group_id', existing_type=sa.Integer(), nullable=False)
            batch.create_foreign_key(f'fk_{table}_group_id_group', 'group', ['group_id'], ['id'])
            if unique:
                batch.create_unique_constraint('uq_appsettings_group_id', ['group_id'])
            else:
                batch.create_index(f'ix_{table}_group_id', ['group_id'], unique=False)
    with op.batch_alter_table('authsession', schema=None) as batch:
        batch.create_foreign_key('fk_authsession_group_id_group', 'group', ['group_id'], ['id'])

    moved = [c for c in ('last_sync_at', 'last_sync_error', 'meta_crawl', 'meta_platform', 'meta_region') if c in _columns('appsettings')]
    if moved:
        with op.batch_alter_table('appsettings', schema=None) as batch:
            for c in moved:
                batch.drop_column(c)
    if 'player_id' in _columns('user'):
        # SQLite rebuilds the table to drop a column with constraints; Postgres drops it in place
        # (rebuilding there would fail: other tables' foreign keys point at "user").
        recreate = 'always' if op.get_bind().dialect.name == 'sqlite' else 'auto'
        with op.batch_alter_table('user', schema=None, recreate=recreate) as batch:
            batch.drop_column('player_id')


def downgrade() -> None:
    raise NotImplementedError("Going back to a single group isn't supported; restore a backup instead.")
