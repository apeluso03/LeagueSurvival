# League of Legends Survival Tracker: Project Spec

Version 0.1 (MVP plan). Owner: Alex Peluso.

## 1. Overview

A web app for a group of friends doing the "League of Legends Survival" challenge.

- The group shares one pool of champions.
- Before each challenge game, every player in the match spins a wheel and gets a short ranked list of champions (3 or 4) from the shared pool.
- Each player plays the highest champion on their list that is still available in champ select.
- **Win:** the team's win count goes up by 1. Nothing is removed.
- **Loss:** every champion that was played in that game is eliminated from the shared pool.
- **Goal:** get as many wins as possible before the pool runs out.
- **Revive bonus:** every 3-game win streak lets each player bring back one eliminated champion.

Riot API integration pulls match data so the app can track stats and remove champions automatically. A challenge mode switch keeps casual games from affecting the pool.

For the MVP the app is used by one person (Alex) on behalf of the group. The design leaves room for a shared online lobby later.

## 2. Goals and Non-Goals

### MVP goals
1. Manage one or more challenge runs, each with its own shared pool.
2. Spin 2 to 5 wheels at once, each giving a player an ordered list of 3 or 4 champions with no overlap between players.
3. Record game results, either automatically from the Riot API or by hand.
4. Eliminate champions on a loss, track wins and streaks, and handle revive tokens.
5. Show player stats (KDA, KP, win rate, best champions, and more).
6. Show the current pool with a toggle to show eliminated champions.
7. A challenge mode on/off switch so casual games are ignored by the challenge.

### Non-goals for MVP
- Multi-user accounts or logins (single user only).
- Real-time multiplayer lobby (planned for later, see Section 12).
- Reading live champ select data (the public Riot API does not offer this).
- Mobile app (web only, but the layout should work on a phone).

## 3. Core Principle: Manual First, Riot Second

Every action the Riot API automates must also be possible by hand. The challenge should be fully playable even if the API key expires, Riot is down, or a match fails to match up. The API layer is an add-on that fills in data and saves clicks. It is never the only way to move the game forward.

This also gives a natural build order: build the manual version first, then add automation.

## 4. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Fast dev setup, type safety for API shapes |
| Styling | Tailwind CSS | Quick to build a clean UI |
| Data fetching | TanStack Query | Caching, refetching, loading states |
| Routing | React Router | One route per tab |
| Backend | FastAPI (Python 3.12) | Familiar stack, async, auto-generated docs at `/docs` |
| ORM | SQLModel (on SQLAlchemy) | Pydantic models double as DB models |
| Database | SQLite for MVP | Zero setup; swap to Postgres later through config |
| Migrations | Alembic | Safe schema changes as features grow |
| HTTP client | httpx (async) | Calls to Riot API and Data Dragon |
| Background jobs | asyncio task or APScheduler inside FastAPI | Match polling; no Redis or Celery needed yet |
| Tests | pytest (backend), Vitest (frontend) | Rules logic must be unit tested |
| Dev setup | Docker Compose (optional) | One command to run both services |

Keep the Riot API key on the backend only. The frontend never talks to Riot directly.

## 5. Project Structure

```
lol-survival/
├── SPEC.md
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   ├── app/
│   │   ├── main.py              # FastAPI app, startup tasks
│   │   ├── config.py            # env settings (RIOT_API_KEY, DB_URL, etc.)
│   │   ├── db.py                # engine, session
│   │   ├── models/              # SQLModel tables
│   │   ├── schemas/             # request/response models
│   │   ├── routers/             # players, runs, pool, spins, games, stats, settings, sync
│   │   ├── services/
│   │   │   ├── ddragon.py       # champion list and images
│   │   │   ├── riot_client.py   # Account-V1, Match-V5, rate limiting
│   │   │   ├── spin.py          # random draw logic
│   │   │   ├── matcher.py       # links Riot matches to challenge games
│   │   │   ├── rules.py         # elimination, streaks, revive tokens
│   │   │   └── stats.py         # stat calculations
│   │   └── jobs/
│   │       └── poller.py        # checks for new matches
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── api/                 # typed API client
        ├── types/
        ├── components/          # Wheel, ChampionCard, PlayerCard, ModeToggle, ...
        ├── pages/
        │   ├── WheelsPage.tsx
        │   ├── StatsPage.tsx
        │   ├── PoolPage.tsx
        │   ├── HistoryPage.tsx
        │   └── SettingsPage.tsx
        └── hooks/
```

## 6. Key Concepts

- **Player:** a friend in the group, linked to a Riot ID (`gameName#tagLine`).
- **Run:** one full attempt at the challenge. Has its own pool, win count, and streak. Lets the group restart without losing history.
- **Pool:** the set of champions in a run, each marked alive or eliminated.
- **Spin:** one press of "Spin" for 2 to 5 players. Creates a Challenge Game.
- **Challenge Game:** one game of the challenge. Holds each player's option list, which champion they ended up playing, and the result.
- **Challenge Mode:** global on/off switch. When off, spins are "practice spins" that do not create Challenge Games, and imported matches never affect the pool.
- **Revive Token:** earned by a 3-game win streak. Spent to bring one eliminated champion back.

## 7. Game Rules (Source of Truth)

These rules live in `services/rules.py` and must be covered by unit tests.

### 7.1 Spinning
- A spin needs 2 to 5 players, picked from the player list.
- Each player gets N options, where N is a run setting (default 3, allowed 3 or 4).
- Options are drawn at random from alive champions **without replacement across all players in the spin**, so no two players share an option.
- If the alive pool has fewer than `players x N` champions, the draw shrinks N for everyone evenly (down to 1). If there are fewer alive champions than players, the spin is blocked and the app suggests using revive tokens or ending the run.
- A player can re-roll only through an explicit "Void spin" action, which is logged.

### 7.2 Locking in
- After champ select, the user marks which option each player actually played (option 1, 2, 3, 4, or "other" with a manual pick).
- If the Riot API matches the game first, the played champions are filled in automatically.
- When a win is recorded by hand, any player left unmarked is assumed to have played option 1. A loss needs every player marked, since it decides what gets eliminated.

### 7.3 Results
- **Win:** run win count +1, streak +1. No champions removed.
- **Loss:** every champion actually played by a tracked player in that game is eliminated. Unplayed backup options are not affected. Streak resets to 0.
- **Remake / early surrender before a set time:** game is marked void. No win, no loss, no elimination, streak unchanged. (Detect with `gameEndedInEarlySurrender` or duration under a threshold, default 5 minutes.)
- **Void (manual):** same as remake. Used for disconnects, wrong queue, mistakes.

### 7.4 Streaks and revives
- When the streak reaches 3, 6, 9, and so on, every player who played in that game earns 1 revive token for the current run.
- A token can revive any eliminated champion in the same run. The champion returns to the alive pool right away.
- Tokens do not carry over between runs.
- Spending a token is logged with who used it and which champion they picked.

### 7.5 Ending a run
- A run ends when the group cannot complete a spin (see 7.1) and has no tokens left, or when the user ends it by hand.
- The final score is the total win count. Best streak and champions left are shown as extra stats.

### 7.6 Undo
- Every pool change (eliminate, revive, void) is written as an event. The latest result can be undone, which reverses its events. This protects against wrong auto-matches.

## 8. Data Model

```
Player
  id, display_name, riot_game_name, riot_tag_line, puuid (nullable),
  platform (e.g. "na1"), region (e.g. "americas"), created_at

Champion                      # cached from Data Dragon
  id (string, e.g. "MonkeyKing"), key (int, e.g. 62, matches Riot match data),
  name (e.g. "Wukong"), title, tags (JSON, e.g. ["Fighter"]), image_url, ddragon_version

Run
  id, name, status ("active" | "ended"), options_per_player (3 | 4),
  win_count, current_streak, best_streak, started_at, ended_at

PoolEntry
  run_id, champion_id, status ("alive" | "eliminated"),
  eliminated_at, eliminated_in_game_id, eliminated_by_player_id

ChallengeGame
  id, run_id, created_at, status ("pending" | "won" | "lost" | "void"),
  result_source ("auto" | "manual"), riot_match_id (nullable), resolved_at

SpinAssignment
  id, game_id, player_id, options (JSON, ordered list of champion ids),
  played_champion_id (nullable), played_option_index (nullable)

ReviveToken
  id, run_id, player_id, earned_in_game_id, used_at (nullable),
  revived_champion_id (nullable)

PoolEvent                     # audit log and undo
  id, run_id, game_id (nullable), type ("eliminate" | "revive" | "manual_eliminate" | "manual_revive"),
  champion_id, player_id (nullable), created_at, undone (bool)

RiotMatch                     # raw cache so we never fetch the same match twice
  match_id, queue_id, game_start, game_duration, raw_json, fetched_at

PlayerMatchStats              # one row per tracked player per match
  match_id, player_id, champion_key, team_id, win,
  kills, deaths, assists, team_kills, cs, gold, damage_to_champs,
  vision_score, game_duration, queue_id,
  is_challenge (bool), challenge_game_id (nullable)

AppSettings                   # single row
  challenge_mode (bool), active_run_id, allowed_queue_ids (JSON),
  poll_interval_seconds, remake_threshold_seconds
```

## 9. Riot API Integration

### 9.1 Endpoints used
| Purpose | Endpoint | Host |
|---|---|---|
| Riot ID to PUUID | `GET /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}` | regional (`americas.api.riotgames.com`) |
| Recent match IDs | `GET /lol/match/v5/matches/by-puuid/{puuid}/ids?startTime=&count=` | regional |
| Match details | `GET /lol/match/v5/matches/{matchId}` | regional |
| Champion list | `https://ddragon.leagueoflegends.com/api/versions.json` then `/cdn/{version}/data/en_US/champion.json` | Data Dragon (no key) |
| Champion images | `/cdn/{version}/img/champion/{id}.png` | Data Dragon |

Note: match data uses the numeric champion `key`, while Data Dragon's main id is a string (for example Wukong is `MonkeyKing`). Store both and always join on `key`.

### 9.2 API key
- A development key expires every 24 hours. Fine for building, bad for daily use.
- Apply for a **personal API key** on the Riot Developer Portal for this project. It does not expire but has low rate limits, which is fine for a small group.
- Check the portal for current limits and wrap all calls in a simple rate limiter that respects `429` responses and the `Retry-After` header.

### 9.3 Match polling and auto-matching
The poller runs every `poll_interval_seconds` (default 90) **only while a Challenge Game is pending**, plus a manual "Sync now" button.

Matching steps for a pending Challenge Game:
1. For each player in the game, fetch match IDs since `game.created_at` minus a small buffer.
2. Find a match ID that appears for every tracked player in the game.
3. Fetch that match. Check that:
   - the queue is in `allowed_queue_ids`,
   - all tracked players were on the same team,
   - each player's champion is one of their spin options.
4. If all checks pass: fill in `played_champion_id`, apply the result through `rules.py`, set `result_source = "auto"`.
5. If the match is found but a check fails (wrong champ, wrong queue): do not apply anything. Flag the game as "needs review" in the UI with the match details shown.
6. If no match is found yet: keep waiting.

Every match fetched for a registered player is also saved to `PlayerMatchStats` (with `is_challenge = false` unless linked), so the stats tab can show casual games too.

### 9.4 Challenge mode switch
- **On:** spins create Challenge Games and the matcher can change the pool.
- **Off:** spins are practice only. The matcher never touches the pool. Matches still import for stats, tagged as non-challenge.
- The switch is shown in the header on every tab with a clear color so it is never set wrong by accident.
- Turning the mode off while a game is pending asks whether to void that game or keep it pending.

## 10. Frontend: Tabs and Screens

### 10.1 Wheels tab
- Pick 2 to 5 players (chips or checkboxes, remembers the last group).
- One wheel per player, all spin at once with a single "Spin" button.
- With 100+ champions a normal pie wheel is hard to read. Use a vertical slot-machine reel or a wheel with portraits only and no text. Animation lands on option 1, then options 2 to N slide in below as backups.
- After the spin: each player card shows their ordered list. Buttons to mark which option was played.
- Pending game panel: shows status ("Waiting for match...", "Matched: Win", "Needs review"), with manual Win / Loss / Void buttons as a fallback.
- Header summary: run name, wins, current streak, champions left, tokens available.

### 10.2 Stats tab
- Filter: Challenge only / All tracked games, and Run selector.
- Per-player card:
  - Games, wins, losses, win %
  - KDA ((K + A) / max(D, 1)) and average K / D / A
  - KP (kill participation): (K + A) / team kills
  - CS per minute, damage per minute, vision score per minute
  - Best champions: champions with 2 or more games, sorted by win % then KDA
  - Champions this player has eliminated (challenge only)
- Group leaderboard table, sortable by any column.
- Run summary: total wins, best streak, eliminated count, games played.

### 10.3 Pool tab
- Grid of champion portraits for the active run, with search by name and filter by class tag (Fighter, Mage, etc.).
- Toggle "Show eliminated." Eliminated champions appear greyed out with who played them and when.
- Counter: "X alive / Y total."
- Revive flow: if a player has a token, they pick an eliminated champion and confirm.
- Manual eliminate / revive actions for fixing mistakes (logged as manual events).

### 10.4 History tab
- List of Challenge Games: date, players, champions played, result, auto or manual, link to match details.
- Undo button on the most recent result.

### 10.5 Settings tab
- Players: add, edit, remove. Enter Riot ID and the app looks up the PUUID.
- Runs: start a new run (choose full champion list or a custom subset, choose 3 or 4 options), end a run.
- Allowed queues (Normal Draft, Ranked Solo/Duo, Flex, ARAM, Quickplay, etc.).
- Poll interval, remake threshold.
- Riot API status: key valid or not, last sync time.

## 11. Backend API (first draft)

```
GET    /api/settings
PATCH  /api/settings                       # challenge_mode, allowed queues, etc.

GET    /api/players
POST   /api/players                        # resolves PUUID from Riot ID
PATCH  /api/players/{id}
DELETE /api/players/{id}

GET    /api/champions                      # cached Data Dragon list
POST   /api/champions/refresh              # pull latest patch

GET    /api/runs
POST   /api/runs
GET    /api/runs/{id}                      # includes win count, streak, tokens
POST   /api/runs/{id}/end

GET    /api/runs/{id}/pool?include_eliminated=true
POST   /api/runs/{id}/pool/{champion_id}/eliminate    # manual
POST   /api/runs/{id}/pool/{champion_id}/revive       # manual or token

POST   /api/runs/{id}/spins                # body: player_ids, returns Challenge Game or practice result
GET    /api/games?run_id=
GET    /api/games/{id}
PATCH  /api/games/{id}/assignments         # mark which option each player played
POST   /api/games/{id}/result              # manual: win | loss | void
POST   /api/games/{id}/undo

GET    /api/tokens?run_id=&player_id=
POST   /api/tokens/{id}/use                # body: champion_id

GET    /api/stats/players?run_id=&challenge_only=
GET    /api/stats/players/{id}
POST   /api/sync                           # run the matcher now
```

## 12. Future: Online Lobby (design for it now, build later)

Target: 3 or more friends join a shared lobby from their own devices and each spins their own wheel at the same time.

What to do now so this is easy later:
- Keep all spin and rules logic on the server. The frontend only shows results. That way a spin is just an event the server can send to many clients.
- Keep the API resource-based so a lobby is just another resource (`/api/lobbies`) that groups players and a pending spin.

What it will need later:
- Login. Simple option: Discord OAuth (the group probably already uses Discord). Riot Sign On is possible but requires an approved production app.
- Real-time updates with FastAPI WebSockets: lobby join/leave, "ready" state, each player's spin result, game result.
- Move from SQLite to Postgres and deploy (for example Fly.io, Railway, or Render).
- Permissions: who can void a game, who can end a run.

## 13. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Setup | Repo, FastAPI and Vite apps run, DB migrations work, CI runs tests |
| M1 | Champions and runs | Data Dragon champion import, create a run, Pool tab shows the grid with the eliminated toggle |
| M2 | Manual challenge loop | Wheels tab spins 2 to 5 players with no overlaps, mark played champs, manual Win/Loss/Void, elimination, streaks, revive tokens, undo. **The challenge is fully playable at this point.** |
| M3 | Riot linking and stats | Players link Riot IDs, matches import, Stats tab shows all listed stats |
| M4 | Auto results | Poller and matcher link games, auto elimination, "needs review" flow, challenge mode switch fully enforced |
| M5 | Polish | Wheel animation, History tab, mobile layout, empty and error states |
| M6 | Online lobby | Section 12 |

## 14. Testing Priorities
1. `rules.py`: loss eliminates only played champs, win does not, void changes nothing, streak and token math (3, 6, 9), undo restores the exact previous state.
2. `spin.py`: no duplicates across players, only alive champions, correct shrinking when the pool is small, blocked spin when the pool is too small.
3. `matcher.py`: uses saved sample match JSON files as fixtures. Cases: clean match, wrong champion, wrong queue, players on different teams, remake, no match yet.
4. `stats.py`: KDA with zero deaths, KP with zero team kills, best champions threshold.

## 15. Open Questions
1. When a revive token is earned, does every player in that 3rd win get one, or does the whole team share one?
   **Decided:** every player who played in the streak game gets their own token (3 players = 3 revives). Group members who sat that game out get none.
2. Should a token be usable on a champion someone else lost, or only on champions the token owner lost?
3. Can players trade or gift tokens?
   **Decided:** no. Tokens belong to the player who earned them.
4. Which queues count for the challenge? (Suggested default: Normal Draft and ARAM. ARAM gives random champs, so it may need its own rules or be excluded.)
5. What happens if a friend joins who is not in the app? Should their champion count toward the pool?
6. Should the run end when the pool hits 0, or when a full spin is no longer possible?
7. Should a full 5-player team be required, or can tracked players be mixed with random teammates? (The matcher handles both.)
8. Do auto results apply right away with undo (current plan), or wait for a confirm click?
   **Decided:** apply right away; the latest result can always be undone.

## 16. Ideas Backlog (post-MVP)
- Discord bot or webhook posting spin results and eliminations.
- "Graveyard" page with stats on each eliminated champion.
- Run comparison: compare runs over time.
- Champion role filter (needs a lane data source, since Data Dragon only has class tags).
- Achievements (first pentakill in a run, flawless 5-game streak).
- Shareable run summary image.
