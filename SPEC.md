# League of Legends Survival Tracker: Project Spec

Version 0.2 (MVP plan + Gold and Shop). Owner: Alex Peluso.
Repo: github.com/apeluso03/LeagueSurvival

## 1. Overview

A web app for a group of friends doing the "League of Legends Survival" challenge.

- The group shares one pool of champions.
- Before each challenge game, every player in the match spins a wheel and gets a short ranked list of champions (3 or 4) from the shared pool.
- Each player plays the highest champion on their list that is still available in champ select.
- **Win:** the team's win count goes up by 1. Nothing is removed.
- **Loss:** every champion that was played in that game is eliminated from the shared pool.
- **Goal:** get as many wins as possible before the pool runs out.
- **Revive bonus:** every 3-game win streak lets each player bring back one eliminated champion.
- **Gold and Shop:** players earn gold from their in-game stats in challenge games and spend it on items (Shield, Reroll, Swap, Choose a Champ, Blacklist, Contract).

Riot API integration pulls match data so the app can track stats, award gold, and remove champions automatically. A challenge mode switch keeps casual games from affecting the pool or earning gold.

For the MVP the app is used by one person (Alex, the run owner) on behalf of the group, including buying and using items for other players. The design leaves room for a shared online lobby later, where each player logs in and uses their own shop.

## 2. Goals and Non-Goals

### MVP goals
1. Manage one or more challenge runs, each with its own shared pool.
2. Spin 2 to 5 wheels at once, each giving a player an ordered list of 3 or 4 champions with no overlap between players.
3. Record game results, either automatically from the Riot API or by hand.
4. Eliminate champions on a loss, track wins and streaks, and handle revive tokens.
5. Show player stats (KDA, KP, win rate, best champions, and more).
6. Show the current pool with a toggle to show eliminated champions.
7. A challenge mode on/off switch so casual games are ignored by the challenge.
8. Award gold per player per run from Riot match stats, and let the owner buy and use shop items on each player's behalf.

### Non-goals for MVP
- Multi-user accounts or logins (single user only).
- Real-time multiplayer lobby (planned for later, see Section 12).
- Reading live champ select data (the public Riot API does not offer this).
- Mobile app (web only, but the layout should work on a phone).

## 3. Core Principle: Manual First, Riot Second

Every action the Riot API automates must also be possible by hand. The challenge should be fully playable even if the API key expires, Riot is down, or a match fails to match up. The API layer is an add-on that fills in data and saves clicks. It is never the only way to move the game forward.

The one exception is gold. Gold comes only from Riot match stats. A game whose result was entered by hand can still earn gold later by linking it to its Riot match ID (see 7.7).

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
LeagueSurvival/
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
│   │   ├── routers/             # players, runs, pool, spins, games, stats, shop, settings, sync
│   │   ├── services/
│   │   │   ├── ddragon.py       # champion list and images
│   │   │   ├── riot_client.py   # Account-V1, Match-V5, rate limiting
│   │   │   ├── spin.py          # random draw logic (respects blacklists)
│   │   │   ├── matcher.py       # links Riot matches to challenge games
│   │   │   ├── rules.py         # elimination, shields, streaks, revive tokens
│   │   │   ├── economy.py       # gold calculation from match stats
│   │   │   ├── shop.py          # catalog, purchases, item effects
│   │   │   ├── contracts.py     # contract goal generation and resolution
│   │   │   ├── rating.py        # in-app performance grade (see 7.10)
│   │   │   └── stats.py         # stat calculations
│   │   └── jobs/
│   │       └── poller.py        # checks for new matches
│   └── tests/
└── frontend/
    ├── package.json
    └── src/
        ├── api/                 # typed API client
        ├── types/
        ├── components/          # Wheel, ChampionCard, PlayerCard, ModeToggle, ItemCard, GoldBadge, ...
        ├── pages/
        │   ├── WheelsPage.tsx
        │   ├── StatsPage.tsx
        │   ├── PoolPage.tsx
        │   ├── ShopPage.tsx
        │   ├── HistoryPage.tsx
        │   └── SettingsPage.tsx
        └── hooks/
```

## 6. Key Concepts

- **Player:** a friend in the group, linked to a Riot ID (`gameName#tagLine`).
- **Owner:** the person who created the run. Only the owner can use the Wheels tab, record results, and (in the MVP) act for other players in the shop.
- **Run:** one full attempt at the challenge. Has its own pool, win count, streak, and gold balances. Lets the group restart without losing history.
- **Pool:** the set of champions in a run, each marked alive or eliminated, and optionally shielded.
- **Spin:** one press of "Spin" for 2 to 5 players. Creates a Challenge Game.
- **Challenge Game:** one game of the challenge. Holds each player's option list, which champion they ended up playing, any items used, and the result.
- **Challenge Mode:** global on/off switch. When off, spins are "practice spins" that do not create Challenge Games, and imported matches never affect the pool or earn gold.
- **Revive Token:** earned by a 3-game win streak. Spent to bring one eliminated champion back.
- **Gold:** per-player, per-run currency earned from Riot stats in challenge games. Starts at 0 for every new run.
- **Item:** something bought in the shop. Owned by one player. Only that player's items can be used for that player.

## 7. Game Rules (Source of Truth)

These rules live in `services/rules.py`, `economy.py`, `shop.py`, and `contracts.py` and must be covered by unit tests. All numbers below are defaults stored in run settings so they can be tuned without code changes.

### 7.1 Spinning
- A spin needs 2 to 5 players, picked from the player list.
- Each player gets N options, where N is a run setting (default 3, allowed 3 or 4).
- Options are drawn at random from alive champions **without replacement across all players in the spin**, so no two players share an option.
- A player's armed Blacklist (see 7.8) removes those champions from that player's draw only.
- If the alive pool has fewer than `players x N` champions, the draw shrinks N for everyone evenly (down to 1). If there are fewer alive champions than players, the spin is blocked and the app suggests using revive tokens or ending the run.
- Outside of items, a player can re-roll only through an explicit "Void spin" action by the owner, which is logged.

### 7.2 Locking in
- After champ select, the owner marks which option each player actually played (option 1, 2, 3, 4, or "other" with a manual pick).
- If the Riot API matches the game first, the played champions are filled in automatically.
- Reroll, Swap, and Choose a Champ can only be used after the spin and before a played champion is recorded.

### 7.3 Results
- **Win:** run win count +1, streak +1. No champions removed.
- **Loss:** every champion actually played by a tracked player in that game is eliminated, unless it has a Shield (see 7.8). Unplayed backup options are not affected. Streak resets to 0.
- **Remake / early surrender before a set time:** game is marked void. No win, no loss, no elimination, no gold, streak unchanged, active contracts refunded. (Detect with `gameEndedInEarlySurrender` or duration under a threshold, default 5 minutes.)
- **Void (manual):** same as remake. Used for disconnects, wrong queue, mistakes.

### 7.4 Streaks and revives
- When the streak reaches 3, 6, 9, and so on, every player who played in that game earns 1 revive token for the current run.
- A token can revive any eliminated champion in the same run. The champion returns to the alive pool right away.
- Tokens do not carry over between runs.
- Spending a token is logged with who used it and which champion they picked.

### 7.5 Ending a run
- A run ends when the group cannot complete a spin (see 7.1) and has no tokens left, or when the owner ends it by hand.
- The final score is the total win count. Best streak, champions left, and total gold earned are shown as extra stats.

### 7.6 Undo
- Every pool change (eliminate, revive, shield consumed, void) and every gold change is written as an event. The latest result can be undone, which reverses all of its events: eliminations, consumed shields, gold earned, contract payouts, and revive tokens earned.
- Undoing a result does not undo item purchases or item uses from before the result.

### 7.7 Gold
Gold is earned per player, per challenge game, from that player's Riot match data. Only games played with challenge mode on and linked to a Riot match earn gold. Gold belongs to the run and starts at 0 in every new run.

| Source | Gold | Riot field(s) |
|---|---|---|
| Kill | 10 each | `kills` |
| Assist | 2 each | `assists` |
| Damage | 10 per full 5,000 | `totalDamageDealtToChampions` |
| Support bonus | Healing and shielding added to the damage number | if `teamPosition == "UTILITY"`: `totalHealsOnTeammates + totalDamageShieldedOnTeammates` |
| Vision | 5 per full 10 vision score | `visionScore` |
| Double kill | 25 each | `doubleKills` |
| Triple kill | 50 each | `tripleKills` |
| Quadra kill | 75 each | `quadraKills` |
| Penta kill | 100 each | `pentaKills` |

Multikill bonuses are on top of the 10 gold per kill.

Formula:
```
damage_total = totalDamageDealtToChampions
             + (totalHealsOnTeammates + totalDamageShieldedOnTeammates if support else 0)
gold = 10*kills + 2*assists
     + 10*floor(damage_total / 5000)
     + 5*floor(visionScore / 10)
     + 25*doubleKills + 50*tripleKills + 75*quadraKills + 100*pentaKills
```

Benchmarks used to set shop prices:
- **Average game:** 5/5/7, 15,000 damage, 20 vision = 50 + 14 + 30 + 10 = **about 100 gold**.
- **Good game:** 8/4/10, 20,000 damage, 30 vision, one double kill = 80 + 20 + 40 + 15 + 25 = **about 200 gold** (180 here, more with a multikill or two).

Pricing rule: every item except the Contract costs at least 2 average games (200+ gold).

Notes:
- Gold is the same on a win or a loss.
- Check with a real penta fixture whether Riot also counts that penta in `quadraKills`, `tripleKills`, and `doubleKills`. If it does, decide whether bonuses stack or only the highest counts (see Open Questions).
- Manual results: a game resolved by hand earns no gold until the owner links its Riot match ID ("Link match" on the History tab). Linking pulls the stats and awards gold without changing the result already recorded.
- Every gold change is a row in the gold ledger with a reason (`game`, `contract_payout`, `purchase`, `refund`, `manual_adjust`), so balances are always the sum of the ledger and the UI can show a per-game breakdown.
- The owner can make manual gold adjustments, which are logged.

### 7.8 Shop and items
- Each player has their own inventory for each run. Items cannot be shared, traded, or used on behalf of a different player's inventory. If Alex owns a Reroll, only Alex's roll can be rerolled with it.
- No inventory limit.
- Items are bought with that player's gold. Items do not carry over between runs.
- In the MVP, the owner buys and uses items for everyone. After online support, each player uses their own.

| Item | Default price | When usable | Effect |
|---|---|---|---|
| Reroll | 250 (about 2.5 average games) | After a spin, before lock-in | Replace the owner's entire option list with a fresh draw. |
| Blacklist | 250 (about 2.5 average games) | Before a spin | Ban up to `ceil(5% of alive pool)` champions from your next roll. |
| Swap | 300 (about 3 average games) | After a spin, before lock-in | Trade your option list with another player in the same spin. |
| Shield | 700 (about 3.5 good games) | Anytime during the run | Place on any alive champion. The next time it would be eliminated by a loss, the shield is used up instead and the champion stays alive. |
| Choose a Champ | 1,600 (about 8 good games) | After a spin, before lock-in | Replace your option list with any single alive champion you pick. |
| Contract | 100 | Before a spin | Get a random goal for your next challenge game. Complete it to earn 300 gold. |

**Shield rules**
- A champion can hold at most one shield. Buying a Shield for an already shielded champion is blocked.
- Any player can shield any alive champion, not only ones they play.
- Shields only block eliminations from a loss. Manual eliminations by the owner ignore shields.
- Shielded champions show a shield icon on the Pool tab, with who placed it.
- A shield stays on its champion until used, even if that champion is not rolled for a long time.

**Reroll rules**
- The new draw excludes the player's old options and every option currently on other players' lists.
- The player's armed Blacklist still applies if it was used for this spin.
- A player can use more than one Reroll on the same spin.

**Swap rules**
- No consent needed from the other player.
- Both lists move as complete lists, in their original order.
- Only the player using the item spends it.

**Choose a Champ rules**
- The player may pick any alive champion that is not on another player's current list in this spin.
- The chosen champion becomes the player's only option. If it gets banned or taken in champ select, the player falls back to "other" with a manual pick and the owner records it (the item is still spent).

**Blacklist rules**
- When used, the player picks between 1 and `ceil(0.05 x alive champions)` champions. Example: 87 alive champions means a cap of 5 (4.35 rounded up).
- The cap is calculated when the Blacklist is used, from the alive count at that moment.
- The blacklist is "armed" and applies only to that player's next spin, then clears.
- Blacklisted champions stay in the pool and can still be rolled by other players.
- If the blacklist leaves too few champions for that player's draw, the draw shrinks like in 7.1.

**Contract rules** (see 7.9)

### 7.9 Contracts
- Cost is 100 gold. Every contract pays out a flat **300 gold** on success and nothing on failure.
- When bought, the app randomly picks one goal type, each with equal weight:

| Goal type | Target |
|---|---|
| Kills | 8+ kills |
| Assists | 15+ assists |
| Outcome | Win the game |
| Rating | A+ or better rating (see 7.10) |

- Since the payout is flat, each goal has one fixed target so no contract is luckier than another. Targets are run settings and can be tuned if one goal turns out much easier than the rest.

- The contract applies to that player's next challenge game that has Riot data. If the player sits out a game, the contract waits.
- One active contract per player per game. A second contract can be bought but waits for the following game.
- Success: payout is added to gold. Failure: the 100 gold cost is lost.
- Void or remake: contract is refunded and returned to the inventory as unused.
- The goal is shown to the player as soon as it is bought, so they know what they are going for.
- Payouts and targets are run settings so they can be balanced later.

### 7.10 Rating
Riot's post-game grade (S+, A+, and so on) is not included in Match-V5 match data. The app computes its own grade in `rating.py`:

```
score = 0.30 * kda_vs_team_avg
      + 0.25 * kill_participation
      + 0.25 * damage_share        (healing/shielding included for supports)
      + 0.20 * vision_vs_team_avg
```

Each part is normalized to 0..1 against the player's own team in that match, then the score maps to a grade scale (S+, S, S-, A+, A, A-, B+ ... D). Thresholds are tuned against real fixtures so the grade feels close to the in-client one. The grade is shown on the History tab and the Stats tab, so players learn what it takes to hit A+.

## 8. Data Model

```
Player
  id, display_name, riot_game_name, riot_tag_line, puuid (nullable),
  platform (e.g. "na1"), region (e.g. "americas"),
  pin_hash (nullable, for future login), discord_id (nullable, for future login),
  created_at

Champion                      # cached from Data Dragon
  id (string, e.g. "MonkeyKing"), key (int, e.g. 62, matches Riot match data),
  name (e.g. "Wukong"), title, tags (JSON, e.g. ["Fighter"]), image_url, ddragon_version

Run
  id, name, status ("active" | "ended"), owner_player_id, lobby_code,
  options_per_player (3 | 4), win_count, current_streak, best_streak,
  shop_config (JSON: item prices, contract targets and payouts, gold rates),
  started_at, ended_at

PoolEntry
  run_id, champion_id, status ("alive" | "eliminated"),
  shield_item_id (nullable),
  eliminated_at, eliminated_in_game_id, eliminated_by_player_id

ChallengeGame
  id, run_id, created_at, status ("pending" | "won" | "lost" | "void"),
  result_source ("auto" | "manual"), riot_match_id (nullable), resolved_at

SpinAssignment
  id, game_id, player_id, options (JSON, ordered list of champion ids),
  original_options (JSON, the list before any items were used),
  played_champion_id (nullable), played_option_index (nullable)

ReviveToken
  id, run_id, player_id, earned_in_game_id, used_at (nullable),
  revived_champion_id (nullable)

GoldLedger                    # balance = sum(amount) per run + player
  id, run_id, player_id, amount (+/-),
  reason ("game" | "contract_payout" | "purchase" | "refund" | "manual_adjust"),
  game_id (nullable), item_id (nullable), breakdown (JSON, per-source amounts for "game"),
  created_at, undone (bool)

InventoryItem
  id, run_id, player_id,
  type ("shield" | "reroll" | "swap" | "choose" | "blacklist" | "contract"),
  price_paid, purchased_at,
  status ("unused" | "armed" | "active" | "used" | "refunded"),
  used_at (nullable), used_in_game_id (nullable),
  target (JSON: champion id for shield/choose, player id for swap, champion ids for blacklist)

Contract
  item_id, goal_type ("kills" | "assists" | "win" | "rating"),
  target (int or grade string), payout,
  game_id (nullable, set when resolved), status ("pending" | "won" | "lost" | "refunded")

PoolEvent                     # audit log and undo
  id, run_id, game_id (nullable),
  type ("eliminate" | "revive" | "manual_eliminate" | "manual_revive" | "shield_placed" | "shield_consumed"),
  champion_id, player_id (nullable), item_id (nullable), created_at, undone (bool)

RiotMatch                     # raw cache so we never fetch the same match twice
  match_id, queue_id, game_start, game_duration, raw_json, fetched_at

PlayerMatchStats              # one row per tracked player per match
  match_id, player_id, champion_key, team_id, team_position, win,
  kills, deaths, assists, team_kills,
  double_kills, triple_kills, quadra_kills, penta_kills,
  cs, gold, damage_to_champs, heals_on_teammates, shields_on_teammates,
  vision_score, game_duration, queue_id, rating_grade,
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

All gold, contract, and rating fields come from each participant object in the Match-V5 match details response (see the field list in 7.7).

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
   - each player's champion is one of their final spin options (after items).
4. If all checks pass, in one transaction: fill in `played_champion_id`, apply the result through `rules.py` (including shields), award gold through `economy.py`, resolve contracts through `contracts.py`, and set `result_source = "auto"`.
5. If the match is found but a check fails (wrong champ, wrong queue): do not apply anything. Flag the game as "needs review" in the UI with the match details shown.
6. If no match is found yet: keep waiting.

Every match fetched for a registered player is also saved to `PlayerMatchStats` (with `is_challenge = false` unless linked), so the stats tab can show casual games too. Non-challenge matches never earn gold.

### 9.4 Challenge mode switch
- **On:** spins create Challenge Games, the matcher can change the pool, and matches earn gold.
- **Off:** spins are practice only. The matcher never touches the pool or gold. Items cannot be used on practice spins. Matches still import for stats, tagged as non-challenge.
- The switch is shown in the header on every tab with a clear color so it is never set wrong by accident.
- Turning the mode off while a game is pending asks whether to void that game or keep it pending.

## 10. Frontend: Tabs and Screens

### 10.1 Wheels tab (owner only)
- Pick 2 to 5 players (chips or checkboxes, remembers the last group).
- Before spinning, each player card shows their gold, an armed Blacklist if any, and an active Contract goal if any. Buttons to arm a Blacklist or buy a Contract for that player.
- One wheel per player, all spin at once with a single "Spin" button.
- With 100+ champions a normal pie wheel is hard to read. Use a vertical slot-machine reel or a wheel with portraits only and no text. Animation lands on option 1, then options 2 to N slide in below as backups.
- After the spin: each player card shows their ordered list, plus Reroll / Swap / Choose a Champ buttons that are enabled only if that player owns the item. Using Reroll re-spins just that player's reel.
- Buttons to mark which option was played.
- Pending game panel: shows status ("Waiting for match...", "Matched: Win", "Needs review"), with manual Win / Loss / Void buttons as a fallback.
- After a result: a summary showing eliminations, shields that saved a champion, gold earned per player, and contract outcomes.
- Header summary: run name, wins, current streak, champions left, tokens available.

### 10.2 Stats tab
- Filter: Challenge only / All tracked games, and Run selector.
- Per-player card:
  - Games, wins, losses, win %
  - KDA ((K + A) / max(D, 1)) and average K / D / A
  - KP (kill participation): (K + A) / team kills
  - CS per minute, damage per minute, vision score per minute
  - Average rating grade
  - Best champions: champions with 2 or more games, sorted by win % then KDA
  - Champions this player has eliminated (challenge only)
  - Gold: current balance, total earned, total spent
- Group leaderboard table, sortable by any column (including gold earned).
- Run summary: total wins, best streak, eliminated count, games played, shields used.

### 10.3 Pool tab
- Grid of champion portraits for the active run, with search by name and filter by class tag (Fighter, Mage, etc.).
- Shield icon on shielded champions, with who placed it.
- Toggle "Show eliminated." Eliminated champions appear greyed out with who played them and when.
- Counter: "X alive / Y total" and "Z shielded."
- Revive flow: if a player has a token, they pick an eliminated champion and confirm.
- Shield flow: if a player owns an unused Shield, they pick an alive, unshielded champion and confirm.
- Manual eliminate / revive actions for fixing mistakes (owner only, logged as manual events).

### 10.4 Shop tab
- Player selector at the top (MVP: owner picks whose shop to view; online: locked to the logged-in player).
- Gold balance and a per-game gold history with the breakdown from 7.7 (kills, assists, damage, vision, multikills, contracts).
- Item cards with name, price, short description, and a Buy button disabled when the player cannot afford it.
- Blacklist card shows the current cap ("You can ban up to 5 champions").
- Inventory section: owned items, armed items, active contract and its goal, and used items history.
- Buying a Contract reveals its goal right away with a short animation.

### 10.5 History tab
- List of Challenge Games: date, players, champions played, result, auto or manual, items used, gold earned, rating grades, link to match details.
- "Link match" on manual games to pull Riot stats and award gold.
- Undo button on the most recent result.

### 10.6 Settings tab
- Players: add, edit, remove. Enter Riot ID and the app looks up the PUUID.
- Runs: start a new run (choose full champion list or a custom subset, choose 3 or 4 options), end a run.
- Shop settings for the run: item prices, gold rates, contract targets and payouts, Blacklist percentage.
- Allowed queues (Normal Draft, Ranked Solo/Duo, Flex, Quickplay, etc.).
- Poll interval, remake threshold.
- Riot API status: key valid or not, last sync time.
- Manual gold adjustment per player (logged).

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
PATCH  /api/runs/{id}/shop-config
POST   /api/runs/{id}/end

GET    /api/runs/{id}/pool?include_eliminated=true
POST   /api/runs/{id}/pool/{champion_id}/eliminate    # manual
POST   /api/runs/{id}/pool/{champion_id}/revive       # manual or token

POST   /api/runs/{id}/spins                # body: player_ids, returns Challenge Game or practice result
GET    /api/games?run_id=
GET    /api/games/{id}
PATCH  /api/games/{id}/assignments         # mark which option each player played
POST   /api/games/{id}/result              # manual: win | loss | void
POST   /api/games/{id}/link-match          # body: riot_match_id, awards gold for a manual game
POST   /api/games/{id}/undo

GET    /api/tokens?run_id=&player_id=
POST   /api/tokens/{id}/use                # body: champion_id

GET    /api/runs/{id}/shop                 # catalog with current prices and blacklist cap
GET    /api/runs/{id}/players/{pid}/gold   # balance + ledger
POST   /api/runs/{id}/players/{pid}/gold/adjust      # owner only
GET    /api/runs/{id}/players/{pid}/inventory
POST   /api/runs/{id}/players/{pid}/purchase         # body: item type; contract returns its goal
POST   /api/items/{id}/use                 # body depends on type:
                                           #   shield: champion_id
                                           #   reroll: game_id
                                           #   swap: game_id, other_player_id
                                           #   choose: game_id, champion_id
                                           #   blacklist: champion_ids

GET    /api/stats/players?run_id=&challenge_only=
GET    /api/stats/players/{id}
POST   /api/sync                           # run the matcher now
```

## 12. Future: Online Lobby (design for it now, build later)

Target: 3 or more friends join a shared lobby from their own devices. The owner runs the wheels, and each player manages their own gold, shop, and items.

What to do now so this is easy later:
- Keep all spin, rules, gold, and item logic on the server. The frontend only shows results. That way a spin or an item use is just an event the server can send to many clients.
- Every item use already records which player it belongs to, so switching from "owner acts for everyone" to "players act for themselves" is a permissions change, not a data change.
- Keep the API resource-based so a lobby is just another resource (`/api/lobbies`) that groups players and a pending spin.

Access and login:
- The owner shares the run's **lobby code** (with an optional run password). The code gets someone into the run.
- The player then picks who they are and confirms with their **PIN** (stored as a hash). This is the first login option.
- **Discord login** (OAuth) comes after, linking a Discord account to a Player so no PIN is needed.

What each role can do:

| Action | Owner | Player |
|---|---|---|
| Wheels tab, spins, record results, undo | Yes | No |
| View Stats, Pool, History | Yes | Yes |
| Use own revive tokens | Yes | Yes |
| Shop: buy and use own items, see own gold | Yes | Yes |
| Use items for other players | Yes | No |
| Manual eliminate/revive, gold adjustments, settings | Yes | No |

Item timing online:
- Reroll, Swap, and Choose a Champ show as buttons on the player's own device after the spin. When used, the owner's wheel screen updates live.
- Blacklists and Contracts are set up by the player before the owner spins.

What it will need later:
- Real-time updates with FastAPI WebSockets: lobby join/leave, ready state, spin results, item uses, game results, gold changes.
- Move from SQLite to Postgres and deploy (for example Fly.io, Railway, or Render).

## 13. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Setup | Repo, FastAPI and Vite apps run, DB migrations work, CI runs tests |
| M1 | Champions and runs | Data Dragon champion import, create a run, Pool tab shows the grid with the eliminated toggle |
| M2 | Manual challenge loop | Wheels tab spins 2 to 5 players with no overlaps, mark played champs, manual Win/Loss/Void, elimination, streaks, revive tokens, undo. **The challenge is fully playable at this point.** |
| M3 | Riot linking and stats | Players link Riot IDs, matches import, Stats tab shows all listed stats |
| M4 | Auto results | Poller and matcher link games, auto elimination, "needs review" flow, challenge mode switch fully enforced |
| M5 | Gold and Shop | Gold ledger and calculation, Link match for manual games, Shop tab, all six items, contracts, rating grade, undo covers gold |
| M6 | Polish | Wheel animation, History tab, mobile layout, empty and error states, result summary screen |
| M7 | Online lobby | Lobby code + PIN login, player permissions, live updates (Section 12) |
| M8 | Discord login | Discord OAuth linked to players |

Status note: M0 to M4 are built. Most of M6 (wheel animation, History tab, mobile layout, empty and error states) was built early, together with the visual overhaul in Section 17.

## 14. Testing Priorities
1. `rules.py`: loss eliminates only played champs, win does not, void changes nothing, a shield blocks exactly one elimination and is then gone, streak and token math (3, 6, 9), undo restores the exact previous state including shields.
2. `spin.py`: no duplicates across players, only alive champions, blacklist only affects its owner, correct shrinking when the pool is small, blocked spin when the pool is too small.
3. `economy.py`: gold formula with the example from 7.7, support bonus only for `UTILITY`, floor rounding at 4,999 and 5,000 damage, multikill bonuses, no gold for non-challenge or void games.
4. `shop.py`: can't buy without enough gold, one shield per champion, blacklist cap math (`ceil(0.05 x alive)`, for example 87 alive gives 5, 20 alive gives 1), reroll excludes old and other players' options, swap exchanges full lists, choose blocks champions on other lists, items can't be used outside their timing window, items stay with their owner.
5. `contracts.py`: each goal type resolves correctly, one active contract per game, refund on void, contract waits when the player sits out.
6. `rating.py`: grade thresholds against saved real matches.
7. `matcher.py`: uses saved sample match JSON files as fixtures. Cases: clean match, wrong champion, wrong queue, players on different teams, remake, no match yet, champion changed by an item.
8. `stats.py`: KDA with zero deaths, KP with zero team kills, best champions threshold.

## 15. Open Questions
1. When a revive token is earned, does every player in that 3rd win get one, or does the whole team share one? (Current plan: every player.)
2. Should a revive token be usable on a champion someone else lost, or only on champions the token owner lost?
3. Which queues count for the challenge? (ARAM gives random champs, so it is excluded from the default list.)
4. What happens if a friend joins who is not in the app? Should their champion count toward the pool?
5. Should the run end when the pool hits 0, or when a full spin is no longer possible?
6. Do auto results apply right away with undo (current plan), or wait for a confirm click?
7. Multikills: if Riot counts a penta as a quadra, triple, and double too, should all the bonuses stack (250 total) or only the highest count (100)?
8. Contracts: the "win/lose" goal type is written here as "win the game." Was there also a loss-based goal in mind (for example "lose but still get 10+ kills")?
9. Rating: is the in-app grade (7.10) close enough, or should A+ contracts be dropped if it doesn't feel right after testing?
10. Prices are based on the average (about 100) and good (about 200) game benchmarks in 7.7. Check real gold per game after the first 10 or so games and adjust if the benchmarks are off.

## 16. Ideas Backlog (post-MVP)
- More shop items: Extra Options (2 more backups next spin), buyable Revive, Mystery Box, Gift gold, cosmetics (titles, badges, wheel colors).
- Discord bot or webhook posting spin results, eliminations, shield saves, and contract wins.
- "Graveyard" page with stats on each eliminated champion.
- Run comparison: compare runs over time.
- Champion role filter (needs a lane data source, since Data Dragon only has class tags).
- Achievements (first pentakill in a run, flawless 5-game streak).
- Shareable run summary image.

## 17. Visual Design and UX Overhaul (v0.2)

Goal: the app should feel like a polished companion to the League client, not a spreadsheet. Two influences: the **League client's palette and ornament** (deep navy, hextech blue, gold trim) and **iOS-style shapes and motion** (rounded continuous corners, frosted-glass panels, quick spring-like animations).

### 17.1 Visual language
- **Palette (League client):** background navy-black `#010A13` / `#0A1428`; panels `#0A1428` → `#1E2328` with ~70% opacity and backdrop blur; gold trim `#785A28` / `#C8AA6E` / `#C89B3C`, light gold text `#F0E6D2`; hextech blue accents `#0AC8B9` / `#0397AB` / `#005A82` / `#CDFAFA`. Win = hextech teal, loss = muted red.
- **Type:** a display serif with small caps feel for headings (Cinzel, standing in for the client's Beaufort) and a clean sans for body (Inter, standing in for Spiegel).
- **Shapes:** large radii (16–24px) on panels and sheets, pill-shaped controls and segmented tabs, thin gold hairline borders, soft layered shadows. No hard boxy edges.
- **Motion:** snappy by default (120–200ms, ease-out); buttons compress slightly when pressed; pages fade/slide in; modals rise as sheets; everything respects "reduce motion".

### 17.2 Landing page (`/`)
- Full-screen title page: logo/wordmark, a short tagline, and the active run at a glance (wins, streak, champions left, tokens).
- Large tiles to open each section: Wheels, Champion Pool, Stats, History, Settings.
- A "Sign in" area reserved for online lobby accounts (Section 12); shown as "coming soon" for now.
- The Wheels tab moves to `/wheels`.

### 17.3 Case-opening wheels
- Each player's wheel is a horizontal strip of champion cards sliding past a center marker, like a CS:GO case opening.
- **All wheels spin together, synced:** same start, same duration, all land at the same moment.
- Longer spin for suspense (~6–7 seconds) with a long ease-out; the landing spot varies slightly within the card so it isn't predictable.
- Cards carry a colored strip by champion class (Fighter, Mage, Assassin, Tank, Marksman, Support), like item rarity.
- **Sound effects** (generated in the browser, no audio files): a tick each time a card passes the marker, slowing with the reel, and a reveal chime on landing. One mute toggle, remembered per browser.
- After landing, the winning card glows and the backup options slide in below. "Skip" lands all wheels at once. Reduced-motion users skip straight to the result.

### 17.4 Champion pools
- The Pool tab shows two "pools" instead of a flat grid:
  - **The Pool** (alive champions): a still water surface with round portrait tokens.
  - **The Graveyard** (eliminated): a darker, murkier pool beside/below it.
- **Nothing animates at rest** (an idle Pool tab should cost nothing). The fun comes from interaction:
  - **Hover lift:** the champion under the mouse rises, tilts and glows.
  - **Drag and fling:** portraits can be dragged around just for fun and drift to a stop; dropping one makes a small splash.
  - **Revive flight:** a revived champion arcs out of the Graveyard (spinning, color returning) and splashes into the Pool, landing where it was dropped if it was dragged.
- **Click a portrait** to open its card: art, title, classes, and its numbers — times offered and played this run, wins/losses on it, who eliminated it and when, and group stats from imported Riot matches.
- **Drag to revive:** if any revive tokens are available, dragging a champion from the Graveyard into the Pool revives it (asking whose token to spend). Without tokens, it drifts back.
- Ideas for later: bumping (flung champions knock others aside), a "Stir the pool" button, "Fish one out" (random champion), an occasional single champion surfacing.
- Search highlights matching champions instead of hiding the rest; a compact grid view stays available as a toggle for quick scanning.

### 17.5 Other polish
- Header becomes a frosted bar with a segmented, pill-shaped tab control.
- Toasts and sheets slide up from the bottom; consistent focus rings for keyboard use.
