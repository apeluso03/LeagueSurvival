"""Copy everything from the local SQLite database into a (new, empty) Postgres database.

Run it once when moving to hosting, from the backend folder with its virtualenv:

    cd backend
    .venv/Scripts/python ../scripts/sqlite_to_postgres.py --source survival.db --target "postgresql://USER:PASS@HOST:PORT/DB"

It first brings the target up to the latest schema (the same migrations the app runs), refuses to
write into a database that already has accounts or players, copies every table in an order that
keeps foreign keys happy, moves Postgres's id counters past the copied ids, and checks the counts.
Your SQLite file is only read, never changed.
"""

import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="the SQLite file, e.g. survival.db")
    ap.add_argument("--target", required=True, help="the Postgres URL (Railway: the Postgres service's DATABASE_PUBLIC_URL)")
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    source_path = Path(args.source).resolve()
    if not source_path.is_file():
        print(f"No SQLite file at {source_path}")
        return 2

    # The app's settings read DATABASE_URL; point them at the target before importing the app.
    os.environ["DATABASE_URL"] = args.target
    os.environ["STARTUP_TASKS"] = "false"

    from sqlalchemy import Integer, create_engine, func, select, text
    from sqlmodel import SQLModel

    import app.models  # noqa: F401 - registers every table
    from app.config import get_settings
    from app.main import run_migrations

    target_url = get_settings().database_url
    if not target_url.startswith("postgresql"):
        print("The target must be a Postgres URL")
        return 2

    print("1/4 Bringing the target database up to the latest schema...")
    run_migrations()

    src = create_engine(f"sqlite:///{source_path.as_posix()}")
    dst = create_engine(target_url)
    tables = SQLModel.metadata.sorted_tables  # parents before children

    with dst.connect() as c:
        for name in ("user", "player"):
            t = SQLModel.metadata.tables[name]
            if c.execute(select(func.count()).select_from(t)).scalar():
                print(f"The target already has rows in {name}. Use a new, empty database.")
                return 1

    print("2/4 Copying tables...")
    with src.connect() as s, dst.begin() as d:
        # Fresh databases come with a few default rows (site settings); the copy replaces them.
        for t in reversed(tables):
            d.execute(t.delete())
        for t in tables:
            # Only the columns both sides have (the source is migrated too, so normally all of them).
            src_cols = {r[1] for r in s.execute(text(f'PRAGMA table_info("{t.name}")'))}
            if not src_cols:
                print(f"   {t.name}: not in the source, skipped")
                continue
            cols = [c for c in t.columns if c.name in src_cols]
            rows = [dict(r._mapping) for r in s.execute(select(*cols))]
            for i in range(0, len(rows), args.batch):
                d.execute(t.insert(), rows[i : i + args.batch])
            print(f"   {t.name}: {len(rows)}")

    print("3/4 Moving id counters past the copied ids...")
    with dst.begin() as d:
        for t in tables:
            if "id" not in t.c or len(t.primary_key.columns) != 1 or not isinstance(t.c.id.type, Integer):
                continue
            quoted = '"' + t.name + '"'
            seq = d.execute(text(f"SELECT pg_get_serial_sequence('{quoted}', 'id')")).scalar()
            if seq:
                d.execute(text(f"SELECT setval('{seq}', COALESCE((SELECT MAX(id) FROM {quoted}), 0) + 1, false)"))

    print("4/4 Checking counts...")
    bad = 0
    with src.connect() as s, dst.connect() as d:
        for t in tables:
            try:
                a = s.execute(select(func.count()).select_from(t)).scalar()
            except Exception:  # noqa: BLE001 - table missing in source
                continue
            b = d.execute(select(func.count()).select_from(t)).scalar()
            if a != b:
                bad += 1
                print(f"   MISMATCH {t.name}: source {a}, target {b}")
    print("Done: everything copied." if not bad else f"{bad} table(s) differ; see above.")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
