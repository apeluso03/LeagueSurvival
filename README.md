# LoL Survival Tracker

A web app for running the "League of Legends Survival" challenge with friends: a shared champion pool, spin wheels, eliminations on losses, and revive tokens for win streaks. See [SPEC.md](SPEC.md) for the full design.

**Status:** milestones M0 to M4 are done. The challenge is fully playable by hand, and with a Riot API key and linked players, results apply automatically after each game (with a review step when something looks off, and undo). Polish and the online lobby (M5, M6) are next.

## Running locally

You need Python 3.12+ and Node 22+.

### Quick start (Windows)

From the project folder in PowerShell:

```powershell
.\dev.ps1
```

This sets everything up on the first run. It starts the backend in a second window and the frontend in the current one, then opens http://127.0.0.1:5173 in your browser. Close both windows (or press Ctrl+C) to stop.

### Running the two servers by hand

The backend and the frontend each need **their own terminal**, because each one keeps running.

### Backend (FastAPI, port 8000)

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

On startup the backend applies database migrations and imports the champion list from Data Dragon. The SQLite database is stored at `backend/survival.db`. API docs are at http://localhost:8000/docs.

Settings are read from `.env` (see [.env.example](.env.example)).

### Frontend (Vite + React, port 5173)

```sh
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The dev server forwards `/api` to the backend.

## Tests

```sh
cd backend && pytest          # rules, spins, API
cd frontend && npm test       # helpers
```

## Database migrations

After changing models in `backend/app/models`:

```sh
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

## How to play

1. **Settings:** add your players, then start a run.
2. **Wheels:** pick 2 to 5 players and press Spin. Each player gets a ranked list of 3 or 4 champions, with no repeats between players.
3. After champ select, click the champion each player played (or use "Other..."). Then record Win, Loss, or Void.
4. A loss eliminates the played champions. Every 3-win streak gives each player in that game a revive token, which they spend on the **Pool** tab.
5. Made a mistake? Use Undo on the latest result (Wheels or **History**), or the manual eliminate/revive fixes on the Pool tab.

The header switch toggles challenge mode. When it is off, spins are practice only and change nothing.

## Automatic results (Riot API)

With `RIOT_API_KEY` set and every player in a game linked to their Riot ID, the backend checks Riot every 90 seconds (configurable) while a challenge game is pending. When it finds the finished match it checks that:

1. the queue is one of the allowed challenge queues,
2. everyone was on the same team,
3. it wasn't a remake (remakes void the game), and
4. each player's champion was one of their options.

If all checks pass, the result is applied right away. If one fails, the game is marked **needs review** on the Wheels tab, where you can use the match anyway, skip it, or record the result by hand. Undoing an auto result tells the matcher to ignore that match from then on.
