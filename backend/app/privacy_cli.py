"""Delete Riot data from the command line (works even when the web app isn't running).

    python -m app.privacy_cli forget <puuid> [<puuid> ...]   # a Riot deletion request
    python -m app.privacy_cli forget-file deletion_list.txt   # one PUUID per line
    python -m app.privacy_cli scrub                           # re-scrub stored matches
    python -m app.privacy_cli purge-all                       # everything from Riot (asks first)
"""

import sys

from sqlmodel import Session

from app.db import engine
from app.services import privacy


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("forget", "forget-file", "scrub", "purge-all"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    with Session(engine) as session:
        if cmd == "forget":
            print(privacy.forget_puuids(session, args))
        elif cmd == "forget-file":
            with open(args[0], encoding="utf-8") as f:
                print(privacy.forget_puuids(session, [line.strip() for line in f if line.strip()]))
        elif cmd == "scrub":
            print({"matches_scrubbed": privacy.scrub_stored_matches(session)})
        else:
            if input("Delete ALL Riot data (matches, stats, high-elo data, PUUIDs)? Type DELETE: ") != "DELETE":
                print("Cancelled")
                return 1
            print(privacy.purge_all(session))
        session.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
