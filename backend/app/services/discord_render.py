"""What the Discord bot's messages look like (SPEC 19.3, 19.4): embeds and buttons built from the
group's data. Everything here only reads; posting is jobs/discord_bot.py and routers/discord.py.

Discord limits that shape these: 10 embeds and 5 rows of components per message, 25 options per
menu, 4096 characters per embed description, 25 fields per embed.
"""

from datetime import datetime

from sqlmodel import Session, col, func, select

from app.config import get_settings
from app.models import (
    ChallengeGame,
    Champion,
    InventoryItem,
    LiveGame,
    Player,
    PlayerMatchStats,
    PoolEntry,
    PoolEvent,
    ReviveToken,
    Run,
)
from app.services import achievements, economy, live, meta, rules
from app.services.shop import ITEMS
from app.services.discord_api import EPHEMERAL

BLUE, GOLD, GREEN, RED, GREY = 0x2E9BFF, 0xC8AA6E, 0x2FBF71, 0xE5283C, 0x5B6475
ROLE_NAMES = {"TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid", "BOTTOM": "Bot", "UTILITY": "Support"}
ROLE_SOURCE = {"set": "set by hand", "game": "from the game", "smite": "has Smite"}
FOOTER = {"text": "Hardcore Draft · not endorsed by Riot Games"}
LOW_POOL = 10  # warn when this few champions are left
# Same order as the site's team colours when a player hasn't picked one (frontend/src/lib/teams.ts).
DEFAULT_COLORS = [0x2E9BFF, 0xE5283C, 0xF5B83D, 0x9B6BFF, 0x2FBF71, 0xFF7A3D, 0x37D0E0, 0xFF5FA2]
QUEUES = {400: "Normal Draft", 420: "Ranked Solo/Duo", 440: "Ranked Flex", 490: "Quickplay", 450: "ARAM"}


# --- small helpers ------------------------------------------------------------------------------


def link(path: str) -> str | None:
    base = get_settings().public_url.rstrip("/")
    return f"{base}{path}" if base else None


def color_of(player: Player | None) -> int:
    if player is None:
        return BLUE
    if player.color and player.color.startswith("#") and len(player.color) == 7:
        return int(player.color[1:], 16)
    return DEFAULT_COLORS[(player.id or 0) % len(DEFAULT_COLORS)]


def reply(content: str | None = None, embeds: list | None = None, components: list | None = None, private: bool = False) -> dict:
    """An interaction response's `data` (or a message body)."""
    msg: dict = {"content": content or "", "embeds": embeds or [], "components": components or []}
    if private:
        msg["flags"] = EPHEMERAL
    return msg


def button(label: str, custom_id: str, style: int = 2, disabled: bool = False) -> dict:
    """style: 1 blue, 2 grey, 3 green, 4 red."""
    return {"type": 2, "style": style, "label": label, "custom_id": custom_id, "disabled": disabled}


def link_button(label: str, url: str) -> dict:
    return {"type": 2, "style": 5, "label": label, "url": url}


def row(*items: dict) -> dict:
    return {"type": 1, "components": list(items)}


class Names:
    """Champion and player names (and art) for one message."""

    def __init__(self, session: Session):
        self.session = session
        self._champs: dict[str, Champion] | None = None
        self._players: dict[int, Player] = {}

    def champ(self, cid: str | None) -> Champion | None:
        if self._champs is None:
            self._champs = {c.id: c for c in self.session.exec(select(Champion)).all()}
        return self._champs.get(cid) if cid else None

    def cname(self, cid: str | None) -> str:
        c = self.champ(cid)
        return c.name if c else (cid or "?")

    def player(self, pid: int | None) -> Player | None:
        if pid is None:
            return None
        if pid not in self._players:
            self._players[pid] = self.session.get(Player, pid)
        return self._players[pid]

    def pname(self, pid: int | None) -> str:
        p = self.player(pid)
        return p.display_name if p else "Someone"


def _alive(session: Session, run_id: int) -> tuple[int, int]:
    count = lambda *w: session.exec(select(func.count()).select_from(PoolEntry).where(PoolEntry.run_id == run_id, *w)).one()  # noqa: E731
    return count(PoolEntry.status == "alive"), count()


def _tokens(session: Session, run_id: int) -> int:
    return len(rules.available_tokens(session, run_id))


def run_line(session: Session, run: Run) -> str:
    alive, total = _alive(session, run.id)
    return f"**{run.win_count}** wins · streak **{run.current_streak}** · **{alive}/{total}** alive · **{_tokens(session, run.id)}** tokens"


# --- spins ----------------------------------------------------------------------------------------


def _roles(session: Session, game: ChallengeGame) -> dict[int, dict]:
    row_ = session.get(LiveGame, game.id)
    return live.player_roles(session, game.id, row_)


def spin_intro(session: Session, game: ChallengeGame) -> dict:
    """The line above a spin's reels (the GIF is attached to it)."""
    n = Names(session)
    names = [n.pname(a.player_id) for a in rules.assignments_for(session, game.id)]
    who = ", ".join(names[:-1]) + f" and {names[-1]}" if len(names) > 1 else "".join(names)
    return {"content": f"🎰 **Game {game.id}**: spinning for {who}...", "allowed_mentions": {"parse": []}}


def spin_message(session: Session, game: ChallengeGame) -> dict:
    """One message per spin: everyone's options, edited as picks come in, then locked in, then the
    result. While the game is pending it has the buttons to play from Discord."""
    n = Names(session)
    run = session.get(Run, game.run_id)
    assignments = rules.assignments_for(session, game.id)
    picked = [a for a in assignments if a.played_champion_id]
    shown = [a.played_champion_id or (a.options[0] if a.options else None) for a in assignments]
    real = _roles(session, game)
    champ_roles = {cid: real[a.player_id]["role"] for a, cid in zip(assignments, shown, strict=True) if cid and a.player_id in real}
    comp = meta.suggest_comp(
        session, [c for c in shown if c], None, exclude=sorted({c for a in assignments for c in a.options}), roles=champ_roles
    )
    suggested = {p.champion_id: p for p in comp["picks"]}

    if game.status == "pending":
        all_in = len(picked) == len(assignments)
        state = "Locked in" if all_in else f"Pick phase · {len(picked)}/{len(assignments)} picked"
        color = GOLD if all_in else BLUE
    else:
        state = {"won": "Victory", "lost": "Defeat", "void": "Voided"}[game.status]
        color = {"won": GREEN, "lost": RED, "void": GREY}[game.status]
    header = {
        "title": f"Game {game.id} · {state}",
        "description": run_line(session, run),
        "color": color,
        "footer": FOOTER,
    }
    if comp["bans"] and game.status == "pending":
        header["fields"] = [{"name": "Suggested bans", "value": ", ".join(n.cname(b["champion_id"]) for b in comp["bans"]), "inline": False}]
    embeds = [header]
    for a, cid in zip(assignments, shown, strict=True):
        lines = []
        for i, opt in enumerate(a.options, start=1):
            mark = " ← **playing**" if a.played_champion_id == opt else ""
            lines.append(f"`{i}` {n.cname(opt)}{mark}")
        if a.played_champion_id and a.played_option_index is None:
            lines.append(f"Playing **{n.cname(a.played_champion_id)}** (not one of the options)")
        pick = suggested.get(cid) if cid else None
        r = real.get(a.player_id)
        if r:
            lines.append(f"Role: **{ROLE_NAMES[r['role']]}** ({ROLE_SOURCE[r['source']]})")
        elif pick:
            lines.append(f"Suggested role: {pick.role_name}")
        if pick and pick.runes and pick.runes.get("keystone"):
            lines.append(f"Build: {pick.runes['keystone']['name']}" + (f" · {pick.spells['spells'][0]['name']} + {pick.spells['spells'][1]['name']}" if pick.spells else ""))
        embed = {"author": {"name": n.pname(a.player_id)}, "description": "\n".join(lines), "color": color_of(n.player(a.player_id))}
        champ = n.champ(cid)
        if champ and champ.image_url:
            embed["thumbnail"] = {"url": champ.image_url}
        embeds.append(embed)

    components = []
    if game.status == "pending":
        components.append(
            row(
                {
                    "type": 3,
                    "custom_id": f"hd:role:{game.id}",
                    "placeholder": "Set the role you're in (autofilled? swapped?)",
                    "options": [{"label": "Auto (detect it)", "value": "auto"}]
                    + [{"label": name, "value": role} for role, name in ROLE_NAMES.items()],
                }
            )
        )
        extra = [button("My items", f"hd:items:{game.id}"), button("My build", f"hd:build:{game.id}")]
        url = link("/live")
        if url:
            extra.append(link_button("Watch live", url))
        components.append(row(*extra))
        components.append(
            row(
                button("Win", f"hd:result:{game.id}:win", style=3),
                button("Loss", f"hd:result:{game.id}:loss", style=4),
                button("Void", f"hd:result:{game.id}:void"),
            )
        )
    return reply(embeds=embeds[:10], components=components)


# --- results --------------------------------------------------------------------------------------


def result_message(session: Session, game: ChallengeGame) -> dict:
    """The result: eliminations, shield saves, tokens, gold and grades, and the big moments.
    Edited again when gold arrives from Riot, and when the result is undone."""
    n = Names(session)
    run = session.get(Run, game.run_id)
    if game.status == "pending":
        return reply(
            embeds=[
                {
                    "title": f"Game {game.id} · result undone",
                    "description": "The owner undid this result; the game is waiting for a result again.",
                    "color": GREY,
                    "footer": FOOTER,
                }
            ]
        )
    title = {"won": "Victory", "lost": "Defeat", "void": "Voided"}[game.status]
    color = {"won": GREEN, "lost": RED, "void": GREY}[game.status]
    desc = [run_line(session, run)]
    if game.status == "void" and game.void_reason:
        desc.append(f"Voided: {game.void_reason}")
    gold = economy.game_gold(session, game.id)
    stats = {}
    if game.riot_match_id:
        stats = {p.player_id: p for p in session.exec(select(PlayerMatchStats).where(PlayerMatchStats.match_id == game.riot_match_id)).all()}
    player_lines = []
    moments = []
    for a in rules.assignments_for(session, game.id):
        parts = [f"**{n.pname(a.player_id)}**", n.cname(a.played_champion_id) if a.played_champion_id else "?"]
        s = stats.get(a.player_id)
        if s:
            parts.append(f"{s.kills}/{s.deaths}/{s.assists}")
            if s.rating_grade:
                parts.append(f"**{s.rating_grade}**")
            for kind, label in (("penta_kills", "PENTAKILL"), ("quadra_kills", "quadra kill")):
                if getattr(s, kind):
                    moments.append(f"{label} for {n.pname(a.player_id)} on {n.cname(a.played_champion_id)}")
                    break
        if a.player_id in gold:
            parts.append(f"+{gold[a.player_id]:,} gold")
        player_lines.append(" · ".join(parts))
    fields = [{"name": "Players", "value": "\n".join(player_lines) or "-", "inline": False}]

    events = session.exec(select(PoolEvent).where(PoolEvent.game_id == game.id, col(PoolEvent.undone).is_(False))).all()
    gone = [e for e in events if e.type == "eliminate"]
    saved = [e for e in events if e.type == "shield_consumed"]
    if gone:
        fields.append({"name": "Eliminated", "value": ", ".join(f"{n.cname(e.champion_id)} ({n.pname(e.player_id)})" for e in gone), "inline": False})
    if saved:
        fields.append({"name": "Saved by a shield", "value": ", ".join(n.cname(e.champion_id) for e in saved), "inline": False})
    # The streak as of this game (the run's own numbers move on with later games).
    streak = (game.prev_current_streak or 0) + 1 if game.status == "won" else 0
    tokens = session.exec(select(ReviveToken).where(ReviveToken.earned_in_game_id == game.id)).all()
    if tokens:
        moments.append(f"{streak}-win streak: a revive token for {', '.join(n.pname(t.player_id) for t in tokens)}")
    breakdown = economy.game_gold_breakdown(session, game.id)
    for pid, b in breakdown.items():
        if b.get("contract"):
            moments.append(f"{n.pname(pid)} hit their contract ({b.get('contract_goal') or 'goal'}): +{b['contract']:,} gold")
    if game.status == "won" and streak >= 3 and streak > (game.prev_best_streak or 0):
        moments.append(f"New best streak for this run: {streak}")
    alive, _ = _alive(session, run.id)
    if game.status == "lost" and alive <= LOW_POOL:
        moments.append(f"Only {alive} champion{'s' if alive != 1 else ''} left in the pool")
    if moments:
        fields.append({"name": "Moments", "value": "\n".join(moments), "inline": False})
    if game.status in ("won", "lost") and not game.riot_match_id:
        fields.append({"name": "Gold", "value": "Comes in once the game is found in Riot's match history.", "inline": False})

    embed = {"title": f"Game {game.id} · {title}", "description": "\n".join(desc), "color": color, "fields": fields, "footer": FOOTER}
    url = link("/history")
    if url:
        embed["url"] = url
    latest = rules.latest_game(session, run.id)
    components = [row(button("Undo", f"hd:undo:{game.id}"))] if latest and latest.id == game.id and run.status == "active" else []
    return reply(embeds=[embed], components=components)


# --- live game ------------------------------------------------------------------------------------


def live_message(session: Session, game: ChallengeGame, static: dict | None = None) -> dict:
    """The game-found post, later edited into a small scoreboard while live stats come in."""
    n = Names(session)
    row_ = session.get(LiveGame, game.id)
    out = live.live_out(session, row_, static)
    if out is None:
        return reply(embeds=[{"title": f"Game {game.id} · looking for the game", "color": GREY}])
    st = out.get("state")
    over = out["ended_at"] is not None
    title = f"{'Game over' if over else 'In game'} · Game {game.id}"
    if out["queue_id"] is not None:
        title += f" · {QUEUES.get(out['queue_id'], 'Queue ' + str(out['queue_id']))}"
    lines = []
    if st:
        t = st["game_time"]
        blue, red = st["teams"]["100"], st["teams"]["200"]
        lead = blue["gold"] - red["gold"]
        side = "Blue" if lead > 0 else "Red"
        lines.append(f"`{t // 60}:{t % 60:02d}` · kills **{blue['kills']}** - **{red['kills']}** · " + (f"{side} +{abs(lead) / 1000:.1f}k gold" if lead else "gold even"))
        lines.append(f"Towers {blue['towers']} - {red['towers']} · dragons {len(blue['dragons'])} - {len(red['dragons'])}" + (f" · barons {blue['barons']} - {red['barons']}" if blue["barons"] or red["barons"] else ""))
        for p in st["players"]:
            if p["player_id"] is not None:
                lines.append(f"**{n.pname(p['player_id'])}** {n.cname(p['champion_id'])} · {p['kills']}/{p['deaths']}/{p['assists']} · {p['cs']} cs")
    else:
        for p in out["participants"]:
            if p.get("player_id") is not None:
                spells = " + ".join(s.get("name", "?") for s in p.get("spells", []))
                lines.append(f"**{n.pname(p['player_id'])}** {n.cname(p.get('champion_id'))}" + (f" · {spells}" if spells else ""))
        lines.append("Live stats show up here when the app's backend runs on a PC that's in the game.")
    roles = out.get("roles") or {}
    if roles:
        lines.append("Roles: " + ", ".join(f"{n.pname(int(pid))} {ROLE_NAMES[r['role']]}" for pid, r in roles.items()))
    embed = {"title": title, "description": "\n".join(lines), "color": GREY if over else RED, "footer": FOOTER}
    url = link("/live")
    components = [row(link_button("Watch live", url))] if url and not over else []
    if url:
        embed["url"] = url
    return reply(embeds=[embed], components=components)


# --- runs, trophies, recaps ------------------------------------------------------------------------


def revive_message(session: Session, run_id: int, champion_id: str, player_id: int | None) -> dict:
    n = Names(session)
    run = session.get(Run, run_id)
    embed = {
        "title": f"{n.cname(champion_id)} is back",
        "description": f"{n.pname(player_id)} spent a revive token.\n{run_line(session, run)}",
        "color": GREEN,
        "footer": FOOTER,
    }
    champ = n.champ(champion_id)
    if champ and champ.image_url:
        embed["thumbnail"] = {"url": champ.image_url}
    return reply(embeds=[embed])


def trophies_message(session: Session, unlocks: list[tuple[int, str]]) -> dict:
    n = Names(session)
    lines = []
    for pid, aid in unlocks:
        a = achievements.BY_ID.get(aid)
        if a:
            lines.append(f"{a.icon} **{n.pname(pid)}** unlocked **{a.name}**: {a.description}")
    embed = {"title": "Trophy unlocked" if len(lines) == 1 else "Trophies unlocked", "description": "\n".join(lines), "color": GOLD, "footer": FOOTER}
    url = link("/trophies")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def run_end_message(session: Session, run: Run) -> dict:
    from app.services import recap

    n = Names(session)
    r = recap.run_recap(session, run)
    t = r["totals"]
    desc = [
        f"**{t['wins']}** wins in **{t['games']}** games · best streak **{t['best_streak']}**",
        f"**{t['alive']}/{t['total']}** champions survived · {t['tokens_earned']} revive tokens · {t['shields_saved']} shield saves",
        f"{t['gold_earned']:,} gold earned · {t['gold_spent']:,} spent in the shop",
    ]
    awards = []
    for a in r["awards"]:
        who = n.pname(a["player_id"]) if a["player_id"] else n.cname(a["champion_id"])
        awards.append(f"**{a['title']}**: {who} · {a['text']}")
    embed = {"title": f"Run over · {run.name}", "description": "\n".join(desc), "color": GOLD, "footer": FOOTER}
    if awards:
        embed["fields"] = [{"name": "Awards", "value": "\n".join(awards)[:1024], "inline": False}]
    url = link(f"/runs/{run.id}/recap")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def wrapped_message(session: Session, group_id: int, month: str) -> dict | None:
    from app.services import shame

    w = shame.wrapped(session, month, group_id)
    if not w["games"]:
        return None
    n = Names(session)
    label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
    lines = [
        f"**{w['wins']}** wins in **{w['games']}** games · best streak **{w['best_streak']}**",
        f"**{w['champions_lost']}** champions lost · **{w['items_bought']}** items bought · {w['gold_spent']:,} gold spent",
    ]
    if w["most_played"]:
        mp = w["most_played"]
        lines.append(f"Most played: {n.cname(mp['champion_id'])} ({mp['games']} games)")
    if w["mvp"]:
        lines.append(f"MVP: **{n.pname(w['mvp']['player_id'])}** ({w['mvp']['wins']}/{w['mvp']['games']} won)")
    if w["top_killer"]:
        lines.append(f"Most kills: {n.pname(w['top_killer']['player_id'])} ({w['top_killer']['kills']})")
    if w["feeder"]:
        lines.append(f"Most deaths per game: {n.pname(w['feeder']['player_id'])} ({w['feeder']['avg_deaths']:.1f})")
    if w["pentas"]:
        lines.append(f"Pentakills: {w['pentas']}")
    embed = {"title": f"Wrapped · {label}", "description": "\n".join(lines), "color": GOLD, "footer": FOOTER}
    url = link(f"/wrapped?month={month}")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def nudge_message(game: ChallengeGame, hours: int) -> dict:
    return reply(
        embeds=[
            {
                "title": f"Game {game.id} is still waiting for a result",
                "description": f"It's been about {hours} hours. If Riot can't find it, the run owner can record it with "
                "the buttons on the spin, `/result`, or on the site.",
                "color": GREY,
                "footer": FOOTER,
            }
        ]
    )


def ready_message(session: Session, run: Run, player_ids: list[int], ready: list[int]) -> dict:
    n = Names(session)
    lines = [f"{'✅' if pid in ready else '⬜'} {n.pname(pid)}" for pid in player_ids]
    done = all(pid in ready for pid in player_ids)
    embed = {
        "title": "Everyone's ready" if done else "Ready check",
        "description": "\n".join(lines) or "No players yet.",
        "color": GREEN if done else BLUE,
        "footer": FOOTER,
    }
    return reply(embeds=[embed], components=[row(button("Ready", f"hd:ready:{run.id}", style=3), button("Not yet", f"hd:unready:{run.id}"))])


# --- command replies ------------------------------------------------------------------------------


def run_status(session: Session, run: Run | None) -> dict:
    if run is None:
        return reply("There's no active run. The group owner can start one with `/newrun` or on the site.", private=True)
    pending = rules.pending_game(session, run.id)
    desc = [run_line(session, run), f"Best streak **{run.best_streak}** · {run.options_per_player} options per player"]
    if pending:
        desc.append(f"Game {pending.id} is waiting for a result.")
    embed = {"title": run.name, "description": "\n".join(desc), "color": BLUE, "footer": FOOTER}
    url = link("/")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def pool_status(session: Session, run: Run | None) -> dict:
    if run is None:
        return reply("There's no active run.", private=True)
    n = Names(session)
    alive, total = _alive(session, run.id)
    recent = session.exec(
        select(PoolEvent)
        .where(PoolEvent.run_id == run.id, col(PoolEvent.type).in_(["eliminate", "revive"]), col(PoolEvent.undone).is_(False))
        .order_by(col(PoolEvent.id).desc())
        .limit(8)
    ).all()
    shielded = session.exec(select(PoolEntry).where(PoolEntry.run_id == run.id, col(PoolEntry.shield_item_id).is_not(None))).all()
    lines = [f"**{alive}/{total}** champions alive"]
    if shielded:
        lines.append("Shielded: " + ", ".join(n.cname(e.champion_id) for e in shielded))
    if recent:
        lines.append("")
        lines += [f"{'💀' if e.type == 'eliminate' else '✨'} {n.cname(e.champion_id)} ({n.pname(e.player_id)})" for e in recent]
    embed = {"title": f"Pool · {run.name}", "description": "\n".join(lines), "color": BLUE, "footer": FOOTER}
    url = link("/pool")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def player_stats(session: Session, player: Player, run: Run | None) -> dict:
    from app.services import stats

    n = Names(session)
    s = stats.player_stats(session, [player.id], run.id if run else None)[0]
    lines = [f"**{s.wins}-{s.losses}**" + (f" ({s.win_rate:.0%})" if s.win_rate is not None else "") + f" in {s.games} challenge games"]
    if s.kda is not None:
        lines.append(f"KDA **{s.kda:.2f}** ({s.avg_kills:.1f}/{s.avg_deaths:.1f}/{s.avg_assists:.1f})")
    if s.avg_grade:
        lines.append(f"Average grade **{s.avg_grade}**")
    if s.best_champions:
        lines.append("Best: " + ", ".join(f"{n.cname(c.champion_id)} {c.wins}-{c.games - c.wins}" for c in s.best_champions[:3]))
    if s.eliminated_champions:
        lines.append(f"Champions lost: {len(s.eliminated_champions)}")
    if s.gold_earned is not None:
        lines.append(f"Gold earned this run: {s.gold_earned:,}")
    embed = {"author": {"name": player.display_name}, "description": "\n".join(lines), "color": color_of(player), "footer": FOOTER}
    url = link(f"/players/{player.id}")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def history(session: Session, group_id: int) -> dict:
    n = Names(session)
    runs = select(Run.id).where(Run.group_id == group_id)
    games = session.exec(
        select(ChallengeGame)
        .where(col(ChallengeGame.run_id).in_(runs), ChallengeGame.status != "pending")
        .order_by(col(ChallengeGame.id).desc())
        .limit(8)
    ).all()
    if not games:
        return reply("No games yet.", private=True)
    lines = []
    for g in games:
        mark = {"won": "🟢", "lost": "🔴", "void": "⚪"}[g.status]
        picks = ", ".join(n.cname(a.played_champion_id) for a in rules.assignments_for(session, g.id) if a.played_champion_id)
        lines.append(f"{mark} Game {g.id} · {picks or '-'}")
    embed = {"title": "Recent games", "description": "\n".join(lines), "color": BLUE, "footer": FOOTER}
    url = link("/history")
    if url:
        embed["url"] = url
    return reply(embeds=[embed])


def build(pick, champion: Champion) -> dict:
    """One champion's high-elo build in a role, with the Mobalytics link."""
    lines = []
    if pick.off_role and pick.build_role:
        lines.append(f"Rarely played as {pick.role_name}; this is its {ROLE_NAMES[pick.build_role]} build.")
    r = pick.runes
    if r:
        lines.append(f"**Runes:** {r['keystone']['name'] if r.get('keystone') else '?'} · {r['primary']['name']} / {r['secondary']['name']}")
        lines.append(", ".join(p["name"] for p in r["primary_perks"] + r["secondary_perks"]))
    if pick.spells:
        lines.append("**Spells:** " + " + ".join(s["name"] for s in pick.spells["spells"]))
    if pick.items:
        lines.append("**Core:** " + ", ".join(i["name"] for i in pick.items) + (f" · {pick.boots['name']}" if pick.boots else ""))
    if not lines:
        lines.append("No high-elo build yet for this role.")
    embed = {
        "title": f"{champion.name} · {pick.role_name}",
        "description": "\n".join(lines),
        "url": f"https://mobalytics.gg/lol/champions/{champion.id.lower()}/build",
        "color": GOLD,
        "footer": FOOTER,
    }
    if champion.image_url:
        embed["thumbnail"] = {"url": champion.image_url}
    return reply(embeds=[embed])


def gold_and_items(session: Session, run: Run, player: Player) -> dict:
    balance = economy.balance(session, run.id, player.id)
    items = session.exec(
        select(InventoryItem).where(
            InventoryItem.run_id == run.id, InventoryItem.player_id == player.id, col(InventoryItem.status).in_(["unused", "armed", "active"])
        )
    ).all()
    lines = [f"**{balance:,}** gold"]
    if items:
        lines.append("Items: " + ", ".join(f"{ITEMS[i.type][0]}{' (armed)' if i.status == 'armed' else ''}" for i in items))
    tokens = [t for t in rules.available_tokens(session, run.id) if t.player_id == player.id]
    if tokens:
        lines.append(f"Revive tokens: {len(tokens)}")
    return reply(embeds=[{"author": {"name": player.display_name}, "description": "\n".join(lines), "color": color_of(player)}], private=True)


# --- Daily Statline (SPEC 20) -------------------------------------------------------------------------

_ARROW = {("higher", False): "⬆️", ("lower", False): "⬇️", ("higher", True): "🔼", ("lower", True): "🔽"}


def _clue_line(n: Names, clue: dict) -> str:
    parts = [f"**{n.cname(clue['champion_id'])}**"]
    if clue.get("role"):
        parts.append(ROLE_NAMES.get(clue["role"], clue["role"]))
    if clue.get("duration"):
        parts.append(f"{clue['duration'] // 60}:{clue['duration'] % 60:02d}")
    if clue.get("queue_id") is not None:
        parts.append(QUEUES.get(clue["queue_id"], f"Queue {clue['queue_id']}"))
    return " · ".join(parts)


def _guess_text(q: dict, players: dict[int, str]) -> str:
    out = []
    for g in q["guesses"]:
        if q["id"] == "kda":
            out.append(" / ".join(f"{p['value']}{'✅' if p['hint'] == 'exact' else _ARROW[(p['hint'], p['close'])]}" for p in g["parts"]))
        elif q["id"] == "grade":
            out.append(f"{g['value']}{'✅' if g['correct'] else _ARROW[(g['hint'], g['close'])]}")
        elif q["id"] == "pilot":
            out.append(f"{players.get(g['value'], '?')} {'✅' if g['correct'] else '❌'}")
        else:
            out.append(f"{g['value'].title()} {'✅' if g['correct'] else '❌'}")
    return " · ".join(out)


def daily_view(session: Session, v: dict, private: bool = False) -> dict:
    """One person's Daily Statline: the clue, their guesses with hints, and the next question's
    buttons (or the answer, their score and the day's leaderboard once done)."""
    n = Names(session)
    players = {p["id"]: p["name"] for p in v["players"]}
    lines = [_clue_line(n, v["clue"]), ""]
    for q in v["questions"]:
        if q["guesses"]:
            lines.append(f"**{q['label']}** {_guess_text(q, players)}")
    components = []
    current = next((q for q in v["questions"] if q["id"] == v["current"]), None)
    if current:
        worth = current["worth"]
        extra = " · -1 per wrong guess" if current["tries"] is None and worth > 0 else ""
        lines.append(f"➡️ **{current['label']}** · worth {worth} {'point' if worth == 1 else 'points'}{extra}")
        if current["id"] in ("kda", "grade"):
            lines.append("-# ⬆️⬇️ the answer is higher or lower · 🔼🔽 close (within 2, or one grade)")
        guessed = {g["value"] for g in current["guesses"]} if current["id"] != "kda" else set()
        if current["id"] == "result":
            components.append(row(button("Win", "hd:dq:result:win", style=3), button("Loss", "hd:dq:result:loss", style=4)))
        elif current["id"] == "pilot":
            options = [{"label": p["name"], "value": str(p["id"])} for p in v["players"] if p["id"] not in guessed][:25]
            components.append(row({"type": 3, "custom_id": "hd:dq:pilot", "placeholder": "Who was piloting?", "options": options}))
        elif current["id"] == "kda":
            components.append(row(button("Guess the K/D/A", "hd:dq:kda", style=1)))
        else:
            options = [{"label": g, "value": g} for g in v["grades"] if g not in guessed]
            components.append(row({"type": 3, "custom_id": "hd:dq:grade", "placeholder": "Pick a grade", "options": options}))
    else:
        a = v["answer"]
        k, d, as_ = a["kda"]
        lines += [
            "",
            f"It was **{a['pilot_name']}** · {a['result'].title()} · {k}/{d}/{as_}" + (f" · {a['grade']}" if a["grade"] else ""),
            f"Score **{v['score']}/{v['max_score']}** · streak {v['streak']}",
        ]
        board = v.get("leaderboard") or []
        if board:
            lines.append("Today: " + ", ".join(f"{e['name']} {e['score']}" for e in board[:8]))
        buttons = [button("Share my result", "hd:dq:share", style=1)] if private else []
        url = link("/daily")
        if url:
            buttons.append(link_button("Open on the site", url))
        if buttons:
            components.append(row(*buttons))
    embed = {"title": f"Daily Statline #{v['number']}", "description": "\n".join(lines), "color": GOLD, "footer": FOOTER}
    champ = n.champ(v["clue"]["champion_id"])
    if champ and champ.image_url:
        embed["thumbnail"] = {"url": champ.image_url}
    return reply(embeds=[embed], components=components, private=private)


def daily_post(session: Session, puzzle, yesterday=None) -> dict:
    """The day's announcement: today's clue, and yesterday's answer and best scores."""
    from app.services import daily

    n = Names(session)
    ans = daily.answer(session, puzzle)
    lines = [
        _clue_line(n, ans),
        "Guess the result, who was piloting, the K/D/A and the grade. One go each, only you see your guesses.",
    ]
    if yesterday is not None:
        y = daily.answer(session, yesterday)
        k, d, a = y["kda"]
        lines += ["", f"Yesterday (#{yesterday.number}): **{n.pname(y['pilot'])}** on {n.cname(y['champion_id'])} · {y['result'].title()} · {k}/{d}/{a}" + (f" · {y['grade']}" if y["grade"] else "")]
        board = daily.leaderboard(session, yesterday)
        if board:
            lines.append("Scores: " + ", ".join(f"{e['name']} {e['score']}/{daily.max_score(y)}" for e in board[:8]))
    embed = {"title": f"Daily Statline #{puzzle.number}", "description": "\n".join(lines), "color": GOLD, "footer": FOOTER}
    champ = n.champ(ans["champion_id"])
    if champ and champ.image_url:
        embed["thumbnail"] = {"url": champ.image_url}
    buttons = [button("Play", "hd:dq:open", style=1)]
    url = link("/daily")
    if url:
        buttons.append(link_button("Play on the site", url))
    return reply(embeds=[embed], components=[row(*buttons)])

