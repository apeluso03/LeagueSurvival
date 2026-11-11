"""Clear test data out of a group (services/cleanup.py). Shows what it would do unless --apply.

    python -m app.cleanup_cli                      # every group and what would go
    python -m app.cleanup_cli --group 1            # one group
    python -m app.cleanup_cli --group 1 --apply    # delete it

Removes, for the group: every run except the current one (with all its games, gold and items),
and in the current run, voided games and games from before the run started. Back up the database
first. Against Railway: `railway run python -m app.cleanup_cli ...` from the backend folder.
"""

import argparse

from sqlmodel import Session, col, select

from app.db import engine
from app.models import Group
from app.services import cleanup, rules


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Clear test data out of a group.")
    ap.add_argument("--group", type=int, help="the group id (leave out to list every group)")
    ap.add_argument("--apply", action="store_true", help="delete it (otherwise only show what would go)")
    args = ap.parse_args(argv)
    with Session(engine) as session:
        groups = session.exec(select(Group).order_by(col(Group.id))).all()
        if args.group is not None:
            groups = [g for g in groups if g.id == args.group]
            if not groups:
                print(f"No group {args.group}")
                return 1
        elif args.apply:
            print("Name the group to clean with --group (run without --apply to see them).")
            return 2
        for g in groups:
            print(f"\nGroup {g.id} {g.name!r}")
            p = cleanup.plan(session, g.id)
            print(cleanup.describe(session, p))
            if not args.apply or p.empty:
                continue
            print("Result:", cleanup.apply(session, p))
            session.commit()
            if p.run is not None:
                session.refresh(p.run)
                numbers = rules.game_numbers(session, [p.run.id])
                last = max(numbers.values(), default=0)
                print(f"Now: {p.run.name!r} has games 1 to {last}, {p.run.win_count} wins, streak {p.run.current_streak}")
        if not args.apply:
            print("\nNothing was changed. Add --apply (with --group) to delete the above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
