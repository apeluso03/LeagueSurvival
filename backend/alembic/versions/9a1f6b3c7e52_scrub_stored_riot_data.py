"""scrub stored riot data

Revision ID: 9a1f6b3c7e52
Revises: 3e7a5c20d4f8
Create Date: 2026-10-17 21:00:00.000000

Data only, no schema change. Removes the identities of people who aren't registered players from
matches saved before scrubbing existed (services/privacy.py), and in-game names from saved
live-game summaries. Safe to run again: scrubbing a scrubbed match changes nothing.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.services.privacy import scrub_match


# revision identifiers, used by Alembic.
revision: str = '9a1f6b3c7e52'
down_revision: Union[str, Sequence[str], None] = '3e7a5c20d4f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _load(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    keep = {r[0] for r in bind.execute(sa.text("SELECT puuid FROM player WHERE puuid IS NOT NULL"))}
    for match_id, raw in bind.execute(sa.text("SELECT match_id, raw_json FROM riotmatch")).all():
        data = _load(raw)
        clean = scrub_match(data, keep)
        if clean != data:
            bind.execute(sa.text("UPDATE riotmatch SET raw_json = :raw WHERE match_id = :id"), {"raw": json.dumps(clean), "id": match_id})

    for game_id, state in bind.execute(sa.text("SELECT game_id, state FROM livegame")).all():
        data = _load(state)
        if not data:
            continue
        for p in data.get("players", []):
            p.pop("name", None)
        for e in data.get("events", []):
            for k in ("killer", "victim"):
                if isinstance(e.get(k), str):
                    e[k] = None  # can't tell who it was without the name; the feed shows "Someone"
        bind.execute(sa.text("UPDATE livegame SET state = :s WHERE game_id = :id"), {"s": json.dumps(data), "id": game_id})


def downgrade() -> None:
    """Nothing to undo: removed data isn't kept anywhere."""
