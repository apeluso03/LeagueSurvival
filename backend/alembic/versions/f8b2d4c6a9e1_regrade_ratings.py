"""regrade ratings

Revision ID: f8b2d4c6a9e1
Revises: f1c3a7e92b04
Create Date: 2026-10-22 15:00:00.000000

The grade now compares a player with their teammates (not a team average that includes them), on
cutoffs calibrated from real games (services/rating.py). Regrade every stored game from its saved
match data, including games imported before grades existed. Settled contracts and gold stay as
they were; trophies and average grades follow the new grades.
"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f8b2d4c6a9e1'
down_revision: Union[str, Sequence[str], None] = 'f1c3a7e92b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.services import rating  # the current scorer; a data-only migration

    bind = op.get_bind()
    puuids = dict(bind.execute(sa.text('SELECT id, puuid FROM player WHERE puuid IS NOT NULL')).all())
    rows = bind.execute(sa.text('SELECT match_id, player_id FROM playermatchstats')).all()
    by_match: dict[str, list[int]] = {}
    for match_id, player_id in rows:
        by_match.setdefault(match_id, []).append(player_id)
    for match_id, player_ids in by_match.items():
        raw = bind.execute(sa.text('SELECT raw_json FROM riotmatch WHERE match_id = :m'), {'m': match_id}).scalar()
        if isinstance(raw, str):
            raw = json.loads(raw)
        if not raw:
            continue
        grades = rating.grades_for_match(raw)
        for player_id in player_ids:
            grade = grades.get(puuids.get(player_id))
            if grade:
                bind.execute(
                    sa.text('UPDATE playermatchstats SET rating_grade = :g WHERE match_id = :m AND player_id = :p'),
                    {'g': grade, 'm': match_id, 'p': player_id},
                )


def downgrade() -> None:
    pass  # the old grades aren't kept; nothing to undo in the schema
