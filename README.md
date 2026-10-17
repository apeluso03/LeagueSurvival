# Hardcore Draft

*Spin your champs. Lose them forever.*

A web app for running a hardcore champion challenge in League of Legends with friends: a shared champion pool, spin wheels, eliminations on losses, and revive tokens for win streaks. See [SPEC.md](SPEC.md) for the full design.

Inspired by the hardcore Dead by Daylight challenge streams by Otzdarva and friends. (A fan project; not connected to them, Behaviour Interactive or Riot Games.)

**Status:** milestones M0 to M7 are built:
- the challenge loop, Riot linking, stats and automatic results;
- gold and the shop;
- the esports broadcast look;
- comp and build suggestions, trophies, recaps and the stream overlay;
- accounts with invite links and per-player permissions.

Next come live updates, then groups so anyone can start their own, then hosting. See [Roadmap](#roadmap).

## Features

- **Wheels:** case-opening reels for 2 to 5 players, landing one after another. Each player's backup options are the champions right next to the one they landed on. After the spin you see:
  - each option's quick facts;
  - a suggested role and a high-elo build (runes, summoner spells, core items, boots) for each player;
  - 5 suggested bans: the champions your rolled champs do worst against;
  - a pick bar, then a LOCKED IN moment and a loading-screen view;
  - win and elimination replay moments.

  Before a spin there's a danger meter and survival odds.
- **Live:** after a spin, the app finds your game when it loads and fills in everyone's champion for you. While the game runs, the Live tab shows:
  - the score, game clock and item-gold lead;
  - towers, dragons and other objectives;
  - each lane's matchup with items, spells, KDA and CS;
  - a gold-lead graph, contract progress and a play-by-play feed.
- **Pool:** card grid of the run's champions with sorts and filters, shields, revives and each champion's numbers.
- **Shop:** gold from your in-game stats; Reroll, Blacklist, Swap, Shield, Choose a Champ and Contracts.
- **Stats:** per-player stats and a sortable leaderboard. Each player has their own page with their title, champions and recent games.
- **Trophies:** 22 achievements that unlock titles, plus a Hall of Shame.
- **Wrapped:** a monthly story of your group's games.
- **History:** every game, the pool activity log, Undo, and Link match for hand-recorded games.
- **Run recap:** a post-game stats graphic with awards. You can save it as an image.
- **Stream overlay:** `/overlay`, a see-through page for OBS showing the score, picks and big moments.
- **Accounts:** an owner account, invite links, and each player handling their own gold, shop and items (see below).

## Accounts

The app needs a sign-in. The first time you open it, it asks you to make the **owner account**. That account owns every run made before accounts existed, and it manages the players, the settings and the invites.

- **Inviting friends:** in Settings, under Accounts and invites, make an invite link for each player and send it to them. Each link works once and expires after 7 days. Whoever opens it picks a username and password, and plays as that player.
- **What players can do:** see everything; buy and use their own items; see and spend their own gold; use their own revive tokens; and pick their own team colour and title.
- **What only the run's owner can do:** spins, results, undo, pool fixes and shop settings. The owner can also open every player's shop and use anyone's items, so one person can still run the whole group.
- **Lost passwords:** remove that person's account in Settings and send them a new invite link. Their games, gold and items stay.

Passwords are hashed with scrypt. Sign-ins use an HttpOnly cookie that lasts 30 days. After 5 wrong passwords, that device waits 15 minutes. The full permission table is in SPEC.md section 12.2.

**The stream overlay needs a signed-in browser.** In OBS, right-click the browser source, choose Interact, and sign in once.

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

1. **First run:** make the owner account.
2. **Settings:** add your players, start a run, and send each friend an invite link (Accounts and invites).
3. **Wheels:** pick 2 to 5 players and press Spin. Each player gets a ranked list of 3 or 4 champions, with no repeats between players.
4. After champ select, click the champion each player played (or use "Other..."). Then record Win, Loss, or Void.
5. A loss eliminates the played champions. Every 3-win streak gives each player in that game a revive token, which they spend on the **Pool** tab.
6. Made a mistake? Use Undo on the latest result (Wheels or **History**), or the manual eliminate/revive fixes on the Pool tab.

The header switch toggles challenge mode. When it is off, spins are practice only and change nothing.

## Automatic results (Riot API)

With `RIOT_API_KEY` set and every player in a game linked to their Riot ID, the backend checks Riot every 90 seconds (configurable) while a challenge game is pending. When it finds the finished match it checks that:

1. the queue is one of the allowed challenge queues,
2. everyone was on the same team,
3. it wasn't a remake (remakes void the game), and
4. each player's champion was one of their options.

If all checks pass, the result is applied right away. If one fails, the game is marked **needs review** on the Wheels tab, where you can use the match anyway, skip it, or record the result by hand. Undoing an auto result tells the matcher to ignore that match from then on.

## Gold and the shop

Players earn gold from their stats in challenge games that have Riot data: kills, assists, damage (healing and shielding count for supports), vision and multikills. Gold is per player and per run. Hand-recorded games earn gold once you link their Riot match on the History tab.

Spend it in the **Shop** tab on Reroll, Blacklist, Swap, Shield, Choose a Champ and Contracts. Prices, gold rates and contract goals can be changed per run in Settings. See SPEC.md section 7 for the exact rules.

## Live game tracking

After a spin, the backend looks for your game.

- **Finding it:** with a Riot key, it asks Riot every 30 seconds whether your linked players are in a game together (Spectator API). This works for any of your players.
- **Live stats:** items, KDA, CS, objectives and kills come from the League client's local Live Client Data API, so **they only work when the backend runs on a PC that's in the game.** Set `LIVE_CLIENT_URL=off` to turn that off.
- **Your picks:** either source fills in each player's champion as soon as the game loads, so you don't have to click picks. Picks you set by hand are kept.
- **Gold numbers:** the game only shares gold for its own player, so team and lane gold are estimated from the value of items held, like a broadcast does.
- **No cooldown timers:** summoner spells are shown, but not their cooldowns. Riot's rules restrict tracking those.

## High-elo builds (comp suggestions)

When the Riot key is set, a background job slowly reads recent ranked solo games from the Challenger, Grandmaster and Master ladders. From those it learns which roles, rune pages, core items and summoner spells each champion uses, how often they win, and how each champion does against every other one (for suggested bans). Champion roles also come from [Meraki Analytics](https://www.merakianalytics.com/), so suggestions work before much data is in.

- **Pace:** it makes one Riot call every 2.5 seconds, so the match poller always gets priority.
- **What it keeps:** only the two newest patches.
- **Settings:** you can turn it off and see its progress there.

The details are in SPEC.md section 9.5.

## Roadmap

The goal is a public website: anyone can sign up, start their own group, and run the challenge with their own friends and settings. The steps:

1. **Live updates:** spins, item uses, picks and results show up on every device at once, using WebSockets. *(next)*
2. **Groups:**
   - open sign-up, so anyone can start a group and become its owner;
   - each group gets its own players, runs, settings and invites;
   - your current data moves into one group.
3. **Hosting:**
   - Postgres instead of SQLite;
   - deployed with HTTPS (Fly.io, Railway or Render);
   - backups;
   - background jobs that run once, not once per server.
4. **Public launch:**
   - a production Riot API key and fair match polling across groups;
   - sign-up limits and spam protection;
   - account and data deletion;
   - terms and privacy pages.
5. **Discord:** Discord login and a webhook per group.

The details are in SPEC.md section 12.

## Privacy and Riot's terms

The app follows Riot's API terms and fan-content policy (SPEC.md section 12.6b):

- **Notice:** every page shows Riot's required "Legal Jibber Jabber" notice, and there's a public privacy and terms page at `/legal`.
- **What it keeps:** only registered players are identifiable in saved data. Other players in a match are saved without names or IDs, and the live tracker labels opponents by champion.
- **Deleting data:** Settings, under Privacy and Riot data, can remove one player's Riot data, act on a Riot deletion list, or delete all Riot data. The same works from the command line:

  ```sh
  cd backend
  python -m app.privacy_cli forget <puuid> ...     # or: forget-file list.txt
  python -m app.privacy_cli purge-all              # everything from Riot (asks first)
  ```

## Credits

- **League** display font (`frontend/public/fonts/League.otf`) by [FontGet.com](https://www.fontget.com), free for personal and commercial use.
- Champion data and images from Riot Games' Data Dragon. Hardcore Draft was created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot Games does not endorse or sponsor this project.

