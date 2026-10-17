# Hardcore Draft: Project Spec

Formerly "LoL Survival Tracker": renamed so the name and domain don't use Riot trademarks (12.6b).

Version 0.3 (MVP, Gold and Shop, accounts; plan for a public site with many groups). Owner: Alex Peluso.
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

Each person signs in with their own account. The run's owner runs the wheels and records results, and can still act for everyone (buying and using items for other players), so one person can run the whole group alone. Every other player manages their own gold, shop and items from their own device.

**Long-term goal:** a public website. Anyone can sign up, start their own group and run as its owner, and invite their own friends, each group with its own players and settings. Section 12 has the plan.

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
- Open sign-up and separate groups on one site (planned, see 12.4). Today one site holds one group, and new accounts join only through invite links.
- Real-time updates between devices (planned next, see 12.3).
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
├── dev.ps1                      # Windows quick start: sets up and runs both servers
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                 # migrations (idempotent; see 12.5 on SQLite)
│   ├── app/
│   │   ├── main.py              # FastAPI app, startup tasks (migrations, champion import, jobs)
│   │   ├── config.py            # env settings (RIOT_API_KEY, DATABASE_URL, CORS_ORIGINS, ...)
│   │   ├── db.py                # engine, session
│   │   ├── models/              # SQLModel tables
│   │   ├── schemas/             # request/response models
│   │   ├── routers/
│   │   │   ├── access.py        # who is signed in, and permission checks
│   │   │   ├── account.py       # sign-up, sign-in, invites, account management
│   │   │   ├── fun.py           # trophies, hall of shame, wrapped, high-elo meta, comp suggestions
│   │   │   └── ...              # players, runs, games, tokens, shop, stats, settings, riot, champions
│   │   ├── services/
│   │   │   ├── auth.py          # password hashing, sessions, invites, sign-in throttle
│   │   │   ├── ddragon.py       # champion list and images
│   │   │   ├── riot_client.py   # Account-V1, Match-V5, League-V4, rate limiting
│   │   │   ├── spin.py          # random draw logic (respects blacklists)
│   │   │   ├── matcher.py       # links Riot matches to challenge games
│   │   │   ├── rules.py         # elimination, shields, streaks, revive tokens
│   │   │   ├── economy.py       # gold calculation from match stats
│   │   │   ├── shop.py          # catalog, purchases, item effects
│   │   │   ├── contracts.py     # contract goal generation and resolution
│   │   │   ├── rating.py        # in-app performance grade (see 7.10)
│   │   │   ├── stats.py         # stat calculations, champion lines, option facts
│   │   │   ├── recap.py         # run recap and player profile pages
│   │   │   ├── achievements.py  # trophies and the titles they unlock
│   │   │   ├── shame.py         # hall of shame and monthly Wrapped
│   │   │   └── meta.py          # high-elo crawler data, role and build suggestions
│   │   └── jobs/
│   │       ├── poller.py        # checks for new matches of tracked players
│   │       └── crawler.py       # slowly crawls high-elo matches for build suggestions
│   └── tests/
└── frontend/
    ├── package.json
    ├── public/fonts/            # League display font (see README credits)
    └── src/
        ├── api/                 # typed API client
        ├── types/
        ├── lib/                 # reel math, odds, danger, facts, teams, tiers, sound, ...
        ├── components/          # CaseReel, LowerThird, PickBar, LockIn, WinMoment, BuildStrip, UserMenu, ...
        ├── pages/
        │   ├── LandingPage.tsx, AuthPages.tsx (sign in, set up, invite)
        │   ├── WheelsPage.tsx, PoolPage.tsx, ShopPage.tsx, StatsPage.tsx
        │   ├── TrophiesPage.tsx, WrappedPage.tsx, HistoryPage.tsx
        │   ├── PlayerPage.tsx, RecapPage.tsx, OverlayPage.tsx
        │   └── SettingsPage.tsx, SettingsAccounts.tsx
        └── hooks/               # queries, useAuth (access rules for the UI), items, ...
```

## 6. Key Concepts

- **Player:** a friend in the group, linked to a Riot ID (`gameName#tagLine`).
- **Account (User):** a username and password. Plays as at most one Player. Accounts are made through the first-run setup or an invite link.
- **Site owner:** the first account made on a site. Manages players, invites, settings and every run. (In the public version this role becomes a support admin, and each group has its own owner; see 12.4.)
- **Run owner:** the account that created the run. Spins, records results, undoes, fixes the pool, edits shop settings, and can act for any player in that run (their gold, shop, items and tokens).
- **Invite:** a one-time sign-up link for one Player. Expires after 7 days. Only the site owner can make one.
- **Group (planned, 12.4):** a set of friends with their own players, runs, settings and invites, owned by one account.
- **Run:** one full attempt at the challenge. Has its own pool, win count, streak, and gold balances. Lets the group restart without losing history.
- **Pool:** the set of champions in a run, each marked alive or eliminated, and optionally shielded.
- **Spin:** one press of "Spin" for 2 to 5 players. Creates a Challenge Game.
- **Challenge Game:** one game of the challenge. Holds each player's option list, which champion they ended up playing, any items used, and the result.
- **Challenge Mode:** global on/off switch. When off, spins are "practice spins" that do not create Challenge Games, and imported matches never affect the pool or earn gold.
- **Revive Token:** earned by a 3-game win streak. Spent to bring one eliminated champion back.
- **Gold:** per-player, per-run currency earned from Riot stats in challenge games. Starts at 0 for every new run.
- **Item:** something bought in the shop. Owned by one player. Only that player (or the run owner) can use it.
- **Achievement and title:** trophies unlocked by play (22 so far, see 10.7). Each unlocks a title a player can show on their profile.
- **Team colour:** each player's broadcast colour, used on name bars, reels and charts. Picked in Settings.

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
  pin_hash (nullable, unused), discord_id (nullable, for Discord login later),
  color (nullable, "#rrggbb" team colour), title (nullable, achievement id shown as a title),
  created_at

Champion                      # cached from Data Dragon
  id (string, e.g. "MonkeyKing"), key (int, e.g. 62, matches Riot match data),
  name (e.g. "Wukong"), title, tags (JSON, e.g. ["Fighter"]), image_url, ddragon_version,
  positions (JSON, roles it's played in, most common first; from Meraki Analytics)

Run
  id, name, status ("active" | "ended"), owner_player_id, lobby_code,
  owner_user_id (the account that runs it),
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

AppSettings                   # single row today; one per group later (12.4)
  challenge_mode (bool), active_run_id, allowed_queue_ids (JSON),
  poll_interval_seconds, remake_threshold_seconds, last_used_player_ids (JSON),
  last_sync_at, last_sync_error,
  meta_crawl (bool), meta_platform (e.g. "na1"), meta_region (e.g. "americas")

User                          # a login account
  id, username (unique, lowercase), password_hash (scrypt),
  player_id (nullable, unique: the Player they play as), is_admin (site owner),
  created_at, last_login_at

AuthSession                   # one signed-in browser
  token_hash (SHA-256 of the cookie token, primary key), user_id, created_at, expires_at

Invite                        # one-time sign-up link for a Player
  id, token_hash (SHA-256 of the link token), player_id, created_by_user_id,
  created_at, expires_at, used_at, used_by_user_id, revoked (bool)

MetaMatch                     # a high-elo match already counted (never counted twice)
  match_id, patch, counted_at, extras (bool: spells and matchups counted too)
MetaChampRole                 # games and wins per champion, role and patch
  champion_key, role, patch, games, wins
MetaRunePage                  # same, per rune page ("tree:perks|tree:perks|shards")
  champion_key, role, patch, page, games, wins
MetaItem                      # same, per completed item
  champion_key, role, patch, item_id, games, wins
LiveGame                      # the live game a pending challenge game is played in (9.6)
  game_id, riot_game_id, platform, queue_id, started_at, detected_at, checked_at,
  updated_at, ended_at, our_team, participants (JSON), bans (JSON), state (JSON summary)
MetaSpells                    # same, per summoner spell pair ("4,14", lowest id first)
  champion_key, role, patch, spells, games, wins
MetaMatchup                   # a champion's record against each enemy champion
  champion_key, enemy_key, patch, games, wins                # single row: the crawler's queue and status
  puuids (JSON), next_index, refreshed_at, last_run_at, last_error, matches_counted
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
| Ranked-solo ladders (high-elo crawler) | `GET /lol/league/v4/{challenger,grandmaster,master}leagues/by-queue/RANKED_SOLO_5x5` | platform (`na1.api.riotgames.com`) |
| Items, runes and summoner spells (names, icons) | `/cdn/{version}/data/en_US/item.json`, `runesReforged.json`, `summoner.json` | Data Dragon |
| Live game (champions, spells, runes, bans) | `GET /lol/spectator/v5/active-games/by-summoner/{puuid}` | platform |
| Live stats (items, KDA, CS, events) | `https://127.0.0.1:2999/liveclientdata/allgamedata` (the game client, no key) | the PC playing the game |
| Champion positions (roles) | `https://cdn.merakianalytics.com/riot/lol/resources/latest/en-US/champions.json` | Meraki Analytics (no key) |

Note: match data uses the numeric champion `key`, while Data Dragon's main id is a string (for example Wukong is `MonkeyKing`). Store both and always join on `key`.

All gold, contract, and rating fields come from each participant object in the Match-V5 match details response (see the field list in 7.7).

### 9.2 API key
- A development key expires every 24 hours. Fine for building, bad for daily use.
- Apply for a **personal API key** on the Riot Developer Portal for this project. It does not expire but has low rate limits, which is fine for a small group.
- Check the portal for current limits and wrap all calls in a simple rate limiter that respects `429` responses and the `Retry-After` header.
- **A public site needs a production key.** Personal keys are for a developer and a few friends. Before opening the site to the public (12.4), apply for a production key: Riot reviews the app, its policies page and its use of the data. All Riot calls (poller, crawler, linking) share one rate limiter.

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

### 9.5 High-elo build crawler (comp suggestions)
After a spin, the app suggests a role for each rolled champion and a high-elo build for it (10.1). The data comes from a slow background crawler (`jobs/crawler.py`, `services/meta.py`):

- Every 12 hours it reads the Challenger, Grandmaster and Master ranked-solo ladders (League-V4) for `meta_platform` and keeps up to 400 players, shuffled.
- One player at a time, it fetches their ranked-solo (queue 420) match IDs from the last 7 days (up to 10), then each match it hasn't counted yet.
- Each match adds games and wins per champion and role (`teamPosition`), per rune page (keystone, both trees, all six runes, shards), per completed item, and per summoner spell pair, by patch. It also counts each champion's record against every champion on the enemy team (matchups, for bans). Only the 2 newest patches are kept.
- Matches counted before spells and matchups were tracked (`MetaMatch.extras = false`) are re-fetched first, 10 per crawler step, to fill those in without counting their roles, runes and items twice.
- It waits 2.5 seconds between calls so it never crowds out the match poller, and commits before every Riot call (SQLite allows one writer). It can be turned off in Settings (`meta_crawl`).
- **Roles:** with 20+ high-elo games, a champion's role scores are 80% its high-elo role share and 20% Meraki's position list; with fewer, Meraki alone. The best assignment for the whole team is picked over all permutations. A role played in under 5% of a champion's high-elo games is marked off-role, and its build then comes from the champion's usual role.
- **Builds:** the most played rune page, the 3 most built core items plus boots, and the most taken summoner spell pair (Flash shown second) for that champion and role, with pick and win rates.
- **Suggested bans (5):** enemy champions the rolled champions do worst against. For each rolled champion, its win rate against an enemy is pulled toward its overall win rate by 10 games (so a 0-2 record doesn't outrank 40-60), and an enemy's threat is how far it drags those rates down, added up over the rolled champions. Champions on anyone's option list are never suggested. Team-wide matchups (any role), not lane matchups, since that data fills in much faster.

### 9.6 Live game tracking
A background job (`jobs/live_tracker.py`, `services/live.py`) watches the pending challenge game:

- **Finding the game:** every 30 seconds it asks Spectator-V5 whether the game's linked players are in a game (one call, for the first linked player). It counts only when every linked player is in it, on one team. Once found it checks every 60 seconds and marks the game ended when Riot stops listing it.
- **Auto picks:** as soon as the game is found, each player's played champion is filled in (option index, or "other"). Picks someone already set by hand are kept; a difference shows as a note on the Live tab.
- **Live stats:** every 3 seconds it reads the game client's Live Client Data API on the PC running the backend (`LIVE_CLIENT_URL`, default `https://127.0.0.1:2999`, self-signed; `off` disables it). The game counts when every player with a Riot ID is in it on one team. This also fills in picks, so it works without a Riot key.
- **What is stored** (`LiveGame`, one row per challenge game): Spectator's participants (champion, team, spells, keystone, which of ours) and bans, plus a summary of the latest client data: per player champion, level, KDA, CS, ward score, items and their value, spells, keystone, dead and respawn time; per team kills, item gold, towers, inhibitors, dragons by type, barons, heralds, grubs, Atakhan; the newest 40 events; the gold lead sampled every 30 game seconds; the result once the game ends. The raw client data is not kept.
- **Gold:** the client only shares gold for its own player, so team and lane gold are the value of items held (Data Dragon prices), the usual broadcast estimate.
- **Not tracked:** summoner spell or ultimate cooldowns. Neither API reports them, and Riot's game-integrity rules restrict tracking enemy cooldowns.
- **Hosted version (12.5):** the backend won't be on a player's PC, so the client reader becomes a small companion app one player runs during games, posting the same data to the site.

## 10. Frontend: Tabs and Screens

### 10.1 Wheels tab
- Pick 2 to 5 players (chips or checkboxes, remembers the last group).
- Before spinning, each player card shows their gold, an armed Blacklist if any, and an active Contract goal if any. Buttons to arm a Blacklist or buy a Contract for that player.
- One wheel per player, all spin at once with a single "Spin" button.
- With 100+ champions a normal pie wheel is hard to read. Use a vertical slot-machine reel or a wheel with portraits only and no text. Animation lands on option 1, then options 2 to N slide in below as backups.
- After the spin: each player card shows their ordered list, plus Reroll / Swap / Choose a Champ buttons that are enabled only if that player owns the item. Using Reroll re-spins just that player's reel.
- Buttons to mark which option was played.
- Pending game panel: shows status ("Waiting for match...", "Matched: Win", "Needs review"), with manual Win / Loss / Void buttons as a fallback.
- After a result: a summary showing eliminations, shields that saved a champion, gold earned per player, and contract outcomes.
- Header summary: run name, wins, current streak, champions left, tokens available.

Built since (v0.3):
- **Spin:** each reel is a horizontal case-opening strip. The reels stop one after another (first at 9.5s, then every 0.6s, so a five-player spin lands at about 11.9s) with a gentle top speed. A reroll replays one reel (8s).
- **Backups are the neighbours:** the two champions right next to the landed one on the reel are options #2 and #3 (and #4 when a run uses 4), so what you saw land is what you get.
- **Pick bar:** "2/4 picked" plus each player's state, shown above the cards.
- **After the spin, on one screen:** each player's card shows their options with quick facts ("You 2-0 · Riot 58% of 12 · Group 4-1", "New for you"), the suggested role, and the high-elo build (keystone, trees, summoner spells, 3 core items and boots; see 9.5). The pick bar shows 5 suggested bans with the rolled champions' win rate against each. The result bar (game status, Riot status, Win / Loss / Void / Re-roll) is a single row. It fits a 1920×1080 desktop or a 1536×730 laptop browser window without scrolling.
- **Moments:** LOCKED IN when everyone has picked, then a loading-screen view with each champion's art, role and build. Win and elimination moments play as replay highlights (cards crack and shatter on a loss), with streak banners at 5, 10, then every 10.
- **Before the spin:** a danger meter (how many losses until spins shrink or stop) and survival odds (a Monte Carlo estimate of reaching the next win targets, using each player's shrunk win rate and the revive-token rules).
- **Signed in as a player (not the run owner):** a "Waiting for the owner to spin" panel with your own Blacklist and Contract buttons. The page checks for a new spin every 10 seconds until live updates exist (12.3). After the spin you see everyone's options and builds, but item buttons only on your own card, and the result bar only shows the status.

### 10.1b Live tab (`/live`)
- Shown in the nav with a red dot while a game is live. Before a game starts it explains what will happen; once found through Riot only, it lists both teams' champions, spells, keystones and bans.
- With live stats, a broadcast layout: score bug (kills per side, game clock, item-gold lead, towers, dragons by type, grubs, herald, baron); bans; lane-by-lane rows pairing each player with their opponent (portrait with level and respawn timer, spells, keystone, KDA, CS, all 7 item slots, lane gold and CS difference); our players marked with their team colour, which spin option they're on, and a shield icon if their champion is shielded; a gold-lead graph; contract progress for kills and assists goals; a play-by-play feed.
- The Wheels tab's result bar says "In game · 12:34 · picks filled in from the live game" with a Watch live link. The stream overlay swaps the picks for a live score bar during the game (`?live=0` hides it).

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
- Built as a card grid (v0.3), replacing the water pools of 17.4: large or compact cards, sorts (A–Z, most played, best win rate, recently eliminated, never rolled first), quick filters (shielded, played, never played, on the current spin), class filters, and a collapsible eliminated section. Each card shows short numbers for the run. Players only see Revive and Shield buttons for their own tokens and shields.

### 10.4 Shop tab
- Player selector at the top. Players only see their own shop; the run owner sees a tab per player.
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
- Since v0.3: **Your account** (everyone): username, team colour, change password, sign out. **Accounts and invites** (site owner): an invite link per player, open invites, remove an account. Team colour picker per player. High-elo data status and refresh. Stream overlay link. Players who aren't the owner only see their account section.

### 10.7 Trophies tab
- **Achievements:** 22 trophies in four rarities (bronze, silver, gold, prismatic), computed from history, e.g. First Blood, On Fire (5 wins in a row), Pentakill, Untouchable (win without dying), Flawless (S+ grade), Necromancer (3 revives), Bodyguard (a shield you placed saved a champion), Whale (5,000 gold spent). Each shows who has it and how rare it is, and unlocks a title.
- **Hall of Shame:** worst games by KDA, most deaths, fastest losses, cursed champions (2+ games and a losing record), feeders, reapers (most champions lost) and wasted items. Per run or all time.

### 10.8 Wrapped (monthly)
- A story of slides for one month: games, wins, best and worst moments, each player's numbers, top champions and pentas. Month picker for past months.

### 10.9 Player pages (`/players/:id`)
- Hero with their most played champion's art, team colour, title (the player or the site owner can change it) and Riot ID.
- Record, win rate, KDA and more; champions played; recent games; runs with links to recaps.
- Private to the player and the run owner: their items and the gold-over-time chart.

### 10.10 Run recap (`/runs/:id/recap`)
- A post-game stats graphic: totals, a win/loss timeline, per-player lines and awards (MVP, Cleanest hands, Top marks, Multikill king, Grim reaper, Big spender, First to fall, Survivor, Workhorse). Can be saved as an image.

### 10.11 Stream overlay (`/overlay`)
- A see-through page for OBS (browser source, 1920×1080): score bug, current picks, and the LOCKED IN / VICTORY / ELIMINATED moments. `?picks=0` and `?moments=0` hide parts. Needs a signed-in browser (in OBS: Interact, then sign in once).

### 10.12 Sign-in pages
- `/setup` (only while the site has no accounts): make the owner account and say which player you are.
- `/login`: username and password. After 5 wrong passwords from one device, that device waits 15 minutes.
- `/invite/:token`: "Join as Bea": pick a username and password for that player.
- Every other page needs a signed-in account; signed-out visitors are sent to `/login` (or `/setup`) and come back to the page they asked for.

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

Added since (v0.3):

```
# accounts (signed out)
GET    /api/auth/me                        # who's signed in; setup_needed on a new site
POST   /api/auth/setup                     # first account = site owner (only with no accounts)
POST   /api/auth/login
POST   /api/auth/logout
GET    /api/auth/invites/{token}           # which player an invite is for
POST   /api/auth/register                  # sign up from an invite
# accounts (signed in)
POST   /api/auth/password                  # change password; signs out other browsers
GET    /api/accounts                       # site owner: accounts and open invites
POST   /api/accounts/invites               # site owner: new invite link for a player
DELETE /api/accounts/invites/{id}          # site owner: cancel an invite
DELETE /api/accounts/{id}                  # site owner: remove an account (history stays)

# pages and extras
GET    /api/runs/{id}/recap
GET    /api/runs/{id}/champion-lines       # short numbers for every Pool card
GET    /api/runs/{id}/events               # pool activity log
GET    /api/runs/{id}/economy              # gold and items for every player you may see
DELETE /api/runs/{id}
GET    /api/games/{id}/option-facts        # quick facts under each rolled champion
POST   /api/games/{id}/review              # accept or reject a "needs review" match
GET    /api/players/{id}/profile
POST   /api/players/{id}/link              # retry the Riot ID lookup
GET    /api/champions/{id}/stats
GET    /api/achievements
GET    /api/shame?run_id=
GET    /api/wrapped?month=2026-10
GET    /api/meta/status                    # high-elo crawler status
POST   /api/meta/positions/refresh         # re-import champion roles (Meraki)
POST   /api/comp                           # body: champion_ids, exclude; roles, builds, spells, bans
GET    /api/riot/status?check=
GET    /api/live                           # the live game for the pending challenge game
GET    /api/games/{id}/live
```

Every endpoint except `/api/health` and the signed-out `/api/auth/*` ones needs a session cookie (401 without one). Permissions are checked on the server (`routers/access.py`); the UI only hides what a user can't do. See 12.2.

## 12. Accounts, Groups and Going Public

### 12.1 Accounts (built, v0.3)
- **Sign-up is invite-only today.** The first person to open a new site makes the owner account on `/setup`; it takes over every run made before accounts existed. Everyone else joins through an invite link the site owner makes for their player in Settings.
- **Invites:** one-time, tied to one Player, expire after 7 days. A new link for the same player cancels the old one. Only a SHA-256 of the token is stored, so a link is shown once.
- **Passwords:** scrypt (Python's standard library), 8 to 200 characters. Usernames are 3 to 24 letters, numbers, dots, dashes or underscores, case-insensitive.
- **Sessions:** a random token in an HttpOnly, SameSite=Lax cookie (secure on https), valid for 30 days. Only its SHA-256 is stored. Signing out deletes it on the server; changing your password signs out every other browser.
- **Sign-in throttle:** 5 wrong passwords for one username from one address, or 20 from one address, means a 15-minute wait. A stranger guessing someone's password only locks themselves out. (In memory; a hosted site with several servers needs a shared store.)
- **Lost password:** the site owner removes the account and sends a new invite. The player's games, gold and items stay.

### 12.2 Who can do what (built)

| Action | Site owner | Run owner | Player |
|---|---|---|---|
| View runs, pool, stats, history, trophies, wrapped, recaps | Yes | Yes | Yes |
| Spin, mark picks, record results, undo, review, link match | Yes | That run | No |
| Manual eliminate/revive, adjust gold, shop prices, end or delete run | Yes | That run | No |
| See gold balance and history, inventory; buy and use items; spend revive tokens | Everyone | Everyone in that run | Their own |
| Arm a Blacklist or buy a Contract before a spin | Everyone | Everyone in that run | Their own |
| Change team colour and title | Anyone | No | Their own |
| Create runs; add, edit or remove players; site settings; challenge mode; Riot sync; invites and accounts | Yes | No | No |

Gold *earned* and per-game gold stay public as stats (Stats leaderboard, game results); balances, gold history and owned items are private.

### 12.3 Live updates (next)
Players now sit on their own devices, so changes must show up everywhere at once.
- One WebSocket per signed-in browser (FastAPI), authenticated by the session cookie, subscribed to the runs that user can see.
- Events: spin started (with the strips, so every device plays the same reels), item used (reroll replays that reel everywhere), picks marked, lock-in, result, undo, pool changes, gold changes, player joined.
- The client keeps TanStack Query as the source of truth: an event invalidates or patches the matching queries. The 10-second polling on the Wheels tab goes away.
- Ready check before a spin (optional): players tap "Ready" and the owner sees who is set.

### 12.4 Groups: anyone can start their own (planned)
Goal: anyone can open the site, make an account, start a group, and invite their own friends. Each group runs its own challenge with its own settings, and the creator owns it.

- **New table `Group`:** id, name, owner_user_id, created_at. Players, runs, invites and settings (`AppSettings` becomes one row per group) all get a `group_id`. The active run becomes per group.
- **Membership:** `GroupMember` (group_id, user_id, player_id, role: owner | member). One account can belong to several groups and switches between them; a player belongs to one group.
- **Open sign-up:** `/signup` makes an account with no group; the next screen offers "Start a group" (you become its owner) or "Join with an invite link".
- **Permissions:** 12.2 stays the same with "site owner" replaced by "group owner", scoped to that group. Every query filters by the current group; a request for another group's data is a 404, so ids don't leak which groups exist.
- **Site admin:** the old site-owner flag becomes a support role (see all groups, remove abuse). It does not play in other groups.
- **Shared data stays shared:** champions, Riot match cache, and the high-elo meta are global.
- **Existing data:** a migration puts every current player, run, invite and setting into one group owned by the current site owner.
- **Limits:** caps on groups per account, players per group and runs per group, so one account can't fill the database.

### 12.5 Hosting (planned)
- **Postgres** instead of SQLite (one writer at a time won't hold up with many groups). Migrations must also run on Postgres; the current ones are written to be safe to re-run on SQLite.
- **Host:** a container on Fly.io, Railway or Render, with the frontend built and served from the same domain (so the session cookie stays first-party) or from a CDN with the API on a subdomain.
- **HTTPS everywhere.** Cookies switch to secure automatically on https.
- **Background jobs:** the poller and crawler move out of the web process (or run on exactly one instance) so scaling the web servers doesn't start duplicate jobs.
- **Backups:** daily database backups with a tested restore; migrations take a backup first.
- **Secrets:** `RIOT_API_KEY` and the database URL from the host's secret store, never in the repo.
- **Monitoring:** error tracking and a health check; logs for Riot rate-limit hits.

### 12.6 Riot API at scale (planned)
- **Production key** (see 9.2) before public launch.
- **Fair polling:** one queue of match checks for all groups, only for pending games, ordered by how long each has waited, inside the key's limits. Stats import for idle players runs at a lower priority.
- **Crawler:** stays one global job; its data is shared by every group.
- **Policies:** follow Riot's developer policies (no features that give an in-game advantage beyond what's allowed; show "Not affiliated with Riot Games"; a privacy policy describing what Riot data is stored).

### 12.6b Riot terms compliance (built, v0.3)
Checked against Riot's API Terms and the "Legal Jibber Jabber" fan-content policy:
- **Required notice** on every page (footer, sign-in pages, landing): "Hardcore Draft was created under Riot Games' "Legal Jibber Jabber" policy using assets owned by Riot Games. Riot Games does not endorse or sponsor this project." Plus a public `/legal` page (privacy policy and terms of use).
- **Data minimisation** (`services/privacy.py`): saved matches keep game numbers for every participant but the identity (PUUID) only of registered players; names, PUUIDs, summoner ids and icons of everyone else are removed before saving, and existing data was scrubbed by migration `9a1f6b3c7e52`. A player linked later has their matches fetched again rather than kept in full. Live games store no in-game names: opponents are their champion, ours their player id. The crawler keeps only totals; its PUUID queue is temporary.
- **Deletion:** remove one player's Riot data (Settings, player row), forget a list of PUUIDs from a Riot GDPR deletion request (Settings, Privacy), and delete all Riot data if API access ends (Settings, or `python -m app.privacy_cli purge-all`). The challenge's own records (runs, results, gold, items) stay.
- **Not commercial:** no paywall; shop gold has no real value. No contests or prizes (stated in the terms).
- **Game integrity:** nothing interferes with the game; no cooldown tracking.
- **Name:** renamed to **Hardcore Draft** (no Riot trademarks). The domain must not use them either, e.g. `hardcoredraft.gg`. "League of Legends" may still be named in descriptions, as a plain reference.
- **Still to do before launch:** register a domain; the production key application; delete database backups made before scrubbing.

### 12.7 Safety, privacy and abuse (planned, before public launch)
- Sign-up rate limits per address, plus a CAPTCHA or email check if sign-up spam shows up.
- Optional email on accounts for password reset (today resets go through the group owner).
- Delete my account and export my data; a group owner can delete their group and everything in it.
- Group and player names are user content: length limits, and a way for the site admin to remove abusive ones.
- Terms of use and a privacy policy pages (built: `/legal`; extend for accounts by email once that exists).
- Sign-in throttle moves to a shared store (Redis or the database) once there's more than one server.

### 12.8 Discord (later)
- Discord login (OAuth) as a second way to sign in, linked to an existing account.
- A Discord webhook per group posting spins, eliminations, shield saves, contract wins and run recaps.

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
| M7 | Accounts | Username/password accounts, invite links, per-player permissions (12.1, 12.2) |
| M8 | Live updates | WebSockets: spins, items, picks and results show on every device at once (12.3) |
| M9 | Groups | Open sign-up, anyone can start a group and own its runs, per-group players and settings (12.4) |
| M10 | Hosting | Postgres, deployed with HTTPS, backups, jobs outside the web process (12.5) |
| M11 | Public launch | Production Riot key, fair polling, abuse protection, privacy and terms pages (12.6, 12.7) |
| M12 | Discord | Discord login and per-group webhooks (12.8) |

Status note (v0.3): M0 to M7 are built, plus the extras in Section 18 (esports look, comp and build suggestions, trophies, hall of shame, wrapped, recaps, player pages, stream overlay). The online lobby code + PIN idea from earlier drafts was replaced by accounts and invite links. M8 is next.

## 14. Testing Priorities
1. `rules.py`: loss eliminates only played champs, win does not, void changes nothing, a shield blocks exactly one elimination and is then gone, streak and token math (3, 6, 9), undo restores the exact previous state including shields.
2. `spin.py`: no duplicates across players, only alive champions, blacklist only affects its owner, correct shrinking when the pool is small, blocked spin when the pool is too small.
3. `economy.py`: gold formula with the example from 7.7, support bonus only for `UTILITY`, floor rounding at 4,999 and 5,000 damage, multikill bonuses, no gold for non-challenge or void games.
4. `shop.py`: can't buy without enough gold, one shield per champion, blacklist cap math (`ceil(0.05 x alive)`, for example 87 alive gives 5, 20 alive gives 1), reroll excludes old and other players' options, swap exchanges full lists, choose blocks champions on other lists, items can't be used outside their timing window, items stay with their owner.
5. `contracts.py`: each goal type resolves correctly, one active contract per game, refund on void, contract waits when the player sits out.
6. `rating.py`: grade thresholds against saved real matches.
7. `matcher.py`: uses saved sample match JSON files as fixtures. Cases: clean match, wrong champion, wrong queue, players on different teams, remake, no match yet, champion changed by an item.
8. `stats.py`: KDA with zero deaths, KP with zero team kills, best champions threshold.
9. Accounts and access (`test_auth.py`): setup only once, invites one-time and expiring, only hashes stored, throttle, password change signs out other browsers, and a permission matrix: players can't spin, record results, change settings or touch another player's gold, items or tokens; the run owner can act for everyone.
10. `meta.py`: match counting by patch, role blending and off-role builds, the crawler never holds the database while waiting on Riot.
11. Once groups exist (12.4): no request can read or change another group's data.

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
11. Public site: should gold earned stay visible to the whole group, or become private like balances?
12. Groups: how many players and runs per group, and how many groups per account? Can a player be in two groups at once?
13. Public site: email required at sign-up (for password reset), or optional?
14. Live updates: should players see the reels spin on their own device in sync with the owner's, or just the result?
15. Who can create a run in a group: only the group owner, or any member (who then owns that run)?

## 16. Ideas Backlog (post-MVP)
- More shop items: Extra Options (2 more backups next spin), buyable Revive, Mystery Box, Gift gold, cosmetics (badges, wheel colours).
- Discord bot or webhook posting spin results, eliminations, shield saves, and contract wins (12.8).
- "Graveyard" page with stats on each eliminated champion.
- Run comparison: compare runs over time.
- Ready check before spins and spectator mode for friends not playing (with live updates).
- Public group pages or leaderboards across groups (opt-in).

Done since v0.2: achievements and titles, shareable run recap image, champion roles (Meraki plus high-elo data), hall of shame, monthly Wrapped, stream overlay.

## 17. Visual Design and UX Overhaul (v0.2)

> Superseded in parts by the esports broadcast style in Section 18 (colours, type, shapes, spin timing and the Pool tab). Kept for history.

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

## 18. Esports Broadcast Style and Extras (v0.3)

### 18.1 Look
- **Mood:** sharp, high-energy, built to watch, like a League esports broadcast.
- **Colours:** near-black cool backgrounds; one strong accent, electric blue `#2e9bff`; gold accents to keep the League feel; a team colour per player (picked in Settings) used on name bars, reels, charts and the user chip.
- **Type:** the League display font for headings (FontGet.com, credited in the README) and a clean sans for body text.
- **Shapes:** slanted, angled panels and parallelogram buttons (clip-path); lower-third name bars; broadcast tags ("LIVE", "PICK PHASE", "REPLAY"); a score bug in the header with the run's wins, streak, champions alive and tokens.
- **Screens as broadcast moments:** the reels are a draft-phase screen with a timer; results play as replay highlights; the recap reads like a post-game stats graphic.

### 18.2 Performance rules
Learned while making the reels smooth; keep to them.
- Animate only `transform` and `opacity`. Glows are an opacity fade on a pseudo-element, never an animated `box-shadow`.
- No infinite animations inside clip-path elements (a blinking dot repainted the page ~90 times a second); live dots are static.
- All reels in one spin start together (no fixed start time) and tick sounds are scheduled from the animation's real start.
- Don't refetch every query when a spin starts: seed the cache with the spin response and refresh everything after the reels land.
- Hardware acceleration must be on in the browser; without it the reels stutter whatever the code does.

### 18.3 Reel timing
- Ease-out over 10.5s base, gentle top speed so names can be read as they pass. Reels land one after another 0.6s apart (9.5s to 11.9s). A reroll takes 8s. "Skip" lands everything at once; reduced-motion users skip straight to the result.

### 18.4 Extras built
- Run recap (10.10), player pages (10.9), Trophies and Hall of Shame (10.7), monthly Wrapped (10.8), stream overlay (10.11).
- Auto-result toast with Undo when a result arrives from Riot while you're on another tab.
- Comp suggestions after each spin: roles and high-elo builds (9.5).
- Champion quick facts under each option, item reminders before the spin, streak milestones, danger meter and survival odds (10.1).
- Live game tracking: auto picks from the live game and a broadcast-style Live tab (9.6, 10.1b).
