"""The Hardcore Draft Discord bot (SPEC 19): slash commands and buttons, and turning the event
outbox into posts in each group's server.

- Interactions (commands, buttons, menus, autocomplete) arrive at routers/discord.py, which checks
  Discord's signature and calls `handle`. Everything that changes the run goes through the same
  game rules and permission checks as the site (routers/access.py): a Discord user acts as the
  account that linked their Discord, in the group the server is linked to. Unlinked people can
  look but not act.
- Announcements: jobs/discord_bot.py calls `send_outbox` every few seconds, plus `refresh_live`,
  `post_nudges`, `post_wrapped` now and then. Rendering reads the database; network calls happen
  with no database transaction open (SQLite allows one writer).
"""

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.models import (
    ChallengeGame,
    Champion,
    DiscordLink,
    DiscordMessage,
    EventOutbox,
    Group,
    GroupMember,
    InventoryItem,
    LiveGame,
    Player,
    Run,
    User,
    utcnow,
)
from app.routers.access import Ctx, can_act_for, can_manage
from app.services import achievements, auth, contracts, economy, meta, rules, shop
from app.services import discord_render as render
from app.services.discord_api import DiscordError
from app.services.rules import RuleError
from app.services.stats import group_settings

log = logging.getLogger("uvicorn.error")

# Announcement kinds a group can switch off (DiscordLink.muted), and what each covers.
KINDS = {
    "spins": "Spins and picks",
    "live": "Game found and the live scoreboard",
    "results": "Results, gold and grades",
    "moments": "Revives and trophies",
    "recaps": "Run recaps and the monthly Wrapped",
    "nudges": "Reminders when a game waits hours for a result",
}
MAX_ATTEMPTS = 5
LIVE_EDIT_SECONDS = 45  # edit a live scoreboard at most this often
NUDGE_AFTER = timedelta(hours=3)
ROLES = list(render.ROLE_NAMES)

# Interaction and response types (discord.com/developers/docs/interactions/receiving-and-responding).
PING, COMMAND, COMPONENT, AUTOCOMPLETE = 1, 2, 3, 4
PONG, MESSAGE, DEFER, UPDATE, CHOICES = 1, 4, 5, 7, 8

# --- slash commands -------------------------------------------------------------------------------

STRING, INTEGER = 3, 4


def _opt(name: str, description: str, type_: int = STRING, required: bool = False, **extra) -> dict:
    return {"name": name, "description": description, "type": type_, "required": required, **extra}


_player = lambda name="player", desc="A player in your group": _opt(name, desc, autocomplete=True)  # noqa: E731
_role_choices = [{"name": n, "value": r} for r, n in render.ROLE_NAMES.items()]

COMMANDS = [
    {"name": "run", "description": "The run's score: wins, streak, champions alive, tokens"},
    {"name": "pool", "description": "Champions alive, shields and recent eliminations"},
    {"name": "stats", "description": "A player's challenge stats", "options": [_player()]},
    {
        "name": "build",
        "description": "A champion's high-elo build",
        "options": [_opt("champion", "Champion", required=True, autocomplete=True), _opt("role", "Role", choices=_role_choices)],
    },
    {"name": "live", "description": "The game being played right now"},
    {"name": "history", "description": "Recent games"},
    {"name": "gold", "description": "Your gold, items and revive tokens (only you see it)", "options": [_player()]},
    {
        "name": "shop",
        "description": "Buy an item",
        "options": [
            _opt("item", "What to buy", required=True, choices=[{"name": v[0], "value": k} for k, v in shop.ITEMS.items()]),
            _player(desc="Who it's for (the run owner can buy for anyone)"),
        ],
    },
    {
        "name": "spin",
        "description": "Spin for the players in this game (run owner)",
        "options": [_player("player1", "Player", ), _player("player2", "Player")]
        + [_player(f"player{i}", "Player") for i in range(3, 6)],
    },
    {
        "name": "pick",
        "description": "Mark which option a player is on (run owner; the live game fills these in too)",
        "options": [_opt("option", "Option number", INTEGER, required=True, min_value=1, max_value=4), _player(desc="Whose pick (yours if empty)")],
    },
    {
        "name": "role",
        "description": "The role you're really in, so your build follows it",
        "options": [_opt("role", "Role", required=True, choices=[{"name": "Auto (detect it)", "value": "auto"}, *_role_choices]), _player(desc="Whose role (run owner)")],
    },
    {
        "name": "result",
        "description": "Record the pending game's result (run owner)",
        "options": [_opt("outcome", "Result", required=True, choices=[{"name": n, "value": v} for n, v in (("Win", "win"), ("Loss", "loss"), ("Void", "void"))])],
    },
    {"name": "undo", "description": "Undo the last result (run owner)"},
    {"name": "ready", "description": "Ready check before a spin"},
    {
        "name": "newrun",
        "description": "Start a new run (group owner)",
        "options": [_opt("name", "Run name", required=True, max_length=60), _opt("options", "Options per player", INTEGER, choices=[{"name": "3", "value": 3}, {"name": "4", "value": 4}])],
    },
    {"name": "link", "description": "Link your Discord account to Hardcore Draft"},
]
for _c in COMMANDS:
    _c["contexts"] = [0]  # servers only: a DM has no group
    # The two spin players are required; Discord wants required options first.
    if _c["name"] == "spin":
        for o in _c["options"][:2]:
            o["required"] = True


# --- who is asking ----------------------------------------------------------------------------------


class Denied(Exception):
    """Say this to the person (privately) and stop."""


@dataclass
class Who:
    discord_id: str
    link: DiscordLink | None
    user: User | None = None
    member: GroupMember | None = None
    group: Group | None = None

    @property
    def ctx(self) -> Ctx | None:
        return Ctx(user=self.user, group=self.group, member=self.member) if self.member else None

    @property
    def player_id(self) -> int | None:
        return self.member.player_id if self.member else None


def _who(session: Session, data: dict) -> Who:
    user_json = (data.get("member") or {}).get("user") or data.get("user") or {}
    discord_id = str(user_json.get("id", ""))
    guild_id = data.get("guild_id")
    link = session.exec(select(DiscordLink).where(DiscordLink.guild_id == str(guild_id))).first() if guild_id else None
    who = Who(discord_id=discord_id, link=link)
    if link is None:
        return who
    who.group = session.get(Group, link.group_id)
    who.user = session.exec(select(User).where(User.discord_id == discord_id)).first() if discord_id else None
    if who.user:
        who.member = auth.membership(session, link.group_id, who.user.id)
    return who


def _site(path: str = "/") -> str:
    return render.link(path) or "the Hardcore Draft site"


def _need_member(who: Who) -> Ctx:
    if who.ctx is None:
        if who.user is None:
            raise Denied(f"Link your Discord account first: Settings, Discord on {_site('/settings')}. Then try again.")
        raise Denied("Your account isn't in the group this server is linked to.")
    return who.ctx


def _active_run(session: Session, group_id: int) -> Run | None:
    settings = group_settings(session, group_id)
    run = session.get(Run, settings.active_run_id) if settings.active_run_id else None
    return run if run and run.group_id == group_id else None


def _need_run(session: Session, who: Who) -> Run:
    run = _active_run(session, who.link.group_id)
    if run is None or run.status != "active":
        raise Denied("There's no active run. The group owner can start one with `/newrun` or on the site.")
    return run


def _pending(session: Session, run: Run) -> ChallengeGame:
    game = rules.pending_game(session, run.id)
    if game is None:
        raise Denied("No game is waiting for a result. Spin first.")
    return game


def _game(session: Session, who: Who, game_id: int) -> ChallengeGame:
    game = session.get(ChallengeGame, game_id)
    run = session.get(Run, game.run_id) if game else None
    if run is None or run.group_id != who.link.group_id:
        raise Denied("That game isn't in this server's group.")
    return game


def _need_manager(ctx: Ctx, run: Run) -> None:
    if not can_manage(ctx, run):
        raise Denied("Only the run's owner can do that.")


def _target_player(session: Session, who: Who, ctx: Ctx, run: Run, value: str | None) -> int:
    """The player an action is for: the named one (run owner, or yourself), else your own."""
    if value:
        try:
            pid = int(value)
        except ValueError:
            pid = None
        player = session.get(Player, pid) if pid else None
        if player is None or player.group_id != who.link.group_id:
            player = session.exec(select(Player).where(Player.group_id == who.link.group_id, Player.display_name == value)).first()
        if player is None:
            raise Denied(f"There's no player called {value} in this group.")
        if not can_act_for(ctx, run, player.id):
            raise Denied("You can only do that for your own player.")
        return player.id
    if ctx.player_id is None:
        raise Denied("Your account doesn't play as anyone in this group. Pick a player, or ask the group owner.")
    return ctx.player_id


def _options(data: dict) -> dict:
    return {o["name"]: o.get("value") for o in (data.get("data") or {}).get("options", [])}


# --- handling one interaction ------------------------------------------------------------------------

Followup = Callable[[Callable[[], Session]], Awaitable[dict]]


@dataclass
class Answer:
    """The immediate response, and for slow work, what to fill the "thinking..." reply with."""

    response: dict
    followup: Followup | None = None
    commit: bool = field(default=False)


def _say(text: str, private: bool = True) -> Answer:
    return Answer({"type": MESSAGE, "data": render.reply(text, private=private)})


def handle(session: Session, data: dict) -> Answer:
    """Answer one interaction. Commits the session itself when the run changed."""
    kind = data.get("type")
    if kind == PING:
        return Answer({"type": PONG})
    if not data.get("guild_id"):
        return _say("Use me in your group's Discord server.")
    who = _who(session, data)
    if kind == AUTOCOMPLETE:
        return Answer({"type": CHOICES, "data": {"choices": _autocomplete(session, who, data)}})
    if who.link is None:
        return _say(
            "This server isn't linked to a Hardcore Draft group yet. The group owner can link it from Settings, Discord on "
            f"{_site('/settings')}."
        )
    try:
        if kind == COMMAND:
            answer = _command(session, who, data)
        elif kind == COMPONENT:
            answer = _component(session, who, data)
        else:
            return _say("I don't know that one.")
    except Denied as e:
        session.rollback()
        return _say(str(e))
    except RuleError as e:
        session.rollback()
        return _say(str(e))
    except HTTPException as e:
        session.rollback()
        return _say(str(e.detail))
    if answer.commit:
        session.commit()
    return answer


def _autocomplete(session: Session, who: Who, data: dict) -> list[dict]:
    if who.link is None:
        return []
    focused = next((o for o in (data.get("data") or {}).get("options", []) if o.get("focused")), None)
    if focused is None:
        return []
    typed = str(focused.get("value") or "").lower()
    if focused["name"] == "champion":
        champs = session.exec(select(Champion).order_by(col(Champion.name))).all()
        return [{"name": c.name, "value": c.id} for c in champs if typed in c.name.lower()][:25]
    players = session.exec(select(Player).where(Player.group_id == who.link.group_id).order_by(col(Player.display_name))).all()
    return [{"name": p.display_name, "value": str(p.id)} for p in players if typed in p.display_name.lower()][:25]


def _command(session: Session, who: Who, data: dict) -> Answer:
    name = data["data"]["name"]
    opts = _options(data)
    group_id = who.link.group_id
    msg = lambda m: Answer({"type": MESSAGE, "data": m})  # noqa: E731

    if name == "run":
        return msg(render.run_status(session, _active_run(session, group_id)))
    if name == "pool":
        return msg(render.pool_status(session, _active_run(session, group_id)))
    if name == "history":
        return msg(render.history(session, group_id))
    if name == "live":
        run = _active_run(session, group_id)
        game = rules.pending_game(session, run.id) if run else None
        if game is None or session.get(LiveGame, game.id) is None:
            return _say("No game is being tracked right now.")
        return msg(render.live_message(session, game))
    if name == "link":
        if who.user:
            player = session.get(Player, who.player_id) if who.player_id else None
            return _say(f"You're linked as **{who.user.username}**" + (f", playing as **{player.display_name}**." if player else "."))
        return _say(f"Link your Discord account on {_site('/settings')} (Settings, Discord). It takes one click.")
    if name == "stats":
        if opts.get("player"):
            pid = int(opts["player"]) if str(opts["player"]).isdigit() else None
            player = session.get(Player, pid) if pid else None
        else:
            player = session.get(Player, who.player_id) if who.player_id else None
        if player is None or player.group_id != group_id:
            raise Denied("Pick a player in this group.")
        return msg(render.player_stats(session, player, _active_run(session, group_id)))
    if name == "build":
        return _build_answer(session, opts.get("champion"), opts.get("role"), private=False)

    # Everything below acts on the run: linked members only.
    ctx = _need_member(who)
    if name == "newrun":
        if not ctx.is_owner:
            raise Denied("Only the group's owner can start a run.")
        run = rules.create_run(session, str(opts["name"])[:60], int(opts.get("options") or 3), group_id=group_id)
        run.owner_user_id = ctx.user.id
        settings = group_settings(session, group_id)
        settings.active_run_id = run.id
        session.add_all([run, settings])
        return Answer({"type": MESSAGE, "data": render.reply(f"New run **{run.name}** started. Good luck.")}, commit=True)

    run = _need_run(session, who)
    if name == "gold":
        pid = _target_player(session, who, ctx, run, opts.get("player"))
        return msg(render.gold_and_items(session, run, session.get(Player, pid)))
    if name == "shop":
        pid = _target_player(session, who, ctx, run, opts.get("player"))
        item, contract = shop.purchase(session, run, pid, str(opts["item"]))
        text = f"Bought **{shop.ITEMS[item.type][0]}** for {item.price_paid:,} gold. {economy.balance(session, run.id, pid):,} left."
        if contract:
            text += f" Your contract: **{contracts.describe(contract)}** for {contract.payout:,} gold."
        elif item.type in ("reroll", "swap", "choose"):
            text += " Use it after the next spin (My items on the spin)."
        else:
            text += " Use it on the site."
        return Answer({"type": MESSAGE, "data": render.reply(text, private=True)}, commit=True)
    if name == "spin":
        _need_manager(ctx, run)
        ids = []
        for key in ("player1", "player2", "player3", "player4", "player5"):
            if opts.get(key):
                pid = int(opts[key]) if str(opts[key]).isdigit() else None
                player = session.get(Player, pid) if pid else None
                if player is None or player.group_id != group_id:
                    raise Denied(f"There's no player {opts[key]} in this group.")
                if pid not in ids:
                    ids.append(pid)
        if len(ids) < 2:
            raise Denied("Spin for at least 2 players.")
        settings = group_settings(session, group_id)
        settings.last_used_player_ids = ids
        session.add(settings)
        if not settings.challenge_mode:
            options = rules.draw_options(session, run, ids)
            n = render.Names(session)
            lines = [f"**{n.pname(pid)}**: " + ", ".join(n.cname(c) for c in opts_) for pid, opts_ in zip(ids, options, strict=True)]
            return Answer({"type": MESSAGE, "data": render.reply("Practice spin (challenge mode is off, nothing is saved):\n" + "\n".join(lines))}, commit=True)
        game = rules.create_spin(session, run, ids)
        if _announcing(who.link, "spins"):
            return Answer({"type": MESSAGE, "data": render.reply(f"Spun for game {game.id}. The draft is in <#{who.link.channel_id}>.", private=True)}, commit=True)
        return Answer({"type": MESSAGE, "data": render.spin_message(session, game)}, commit=True)
    if name == "pick":
        # Same rule as the site (SPEC 12.2): only the run owner marks picks.
        _need_manager(ctx, run)
        game = _pending(session, run)
        pid = _target_player(session, who, ctx, run, opts.get("player"))
        return _pick(session, game, pid, int(opts["option"]) - 1)
    if name == "role":
        game = _pending(session, run)
        pid = _target_player(session, who, ctx, run, opts.get("player"))
        return _set_role(session, game, pid, opts["role"])
    if name == "result":
        _need_manager(ctx, run)
        game = _pending(session, run)
        rules.apply_result(session, game, str(opts["outcome"]), source="manual")
        return Answer({"type": MESSAGE, "data": render.reply(f"Game {game.id}: {_RESULT_TEXT[game.status]}.", private=True)}, commit=True)
    if name == "undo":
        _need_manager(ctx, run)
        game = rules.latest_game(session, run.id)
        if game is None or game.status == "pending":
            raise Denied("There's no result to undo.")
        rules.undo_result(session, game)
        return Answer({"type": MESSAGE, "data": render.reply(f"Undid game {game.id}'s result. It's waiting for a result again.", private=True)}, commit=True)
    if name == "ready":
        settings = group_settings(session, group_id)
        players = list(settings.last_used_player_ids or []) or [
            p.id for p in session.exec(select(Player).where(Player.group_id == group_id)).all()
        ]
        old = session.get(DiscordMessage, (group_id, "ready", run.id))
        if old:
            session.delete(old)
        return Answer({"type": MESSAGE, "data": render.ready_message(session, run, players, [])}, commit=True)
    return _say("I don't know that command.")


_RESULT_TEXT = {"won": "win recorded", "lost": "loss recorded", "void": "voided"}


def _pick(session: Session, game: ChallengeGame, player_id: int, index: int) -> Answer:
    rules.set_played(session, game, [rules.Pick(player_id=player_id, option_index=index)])
    a = next(a for a in rules.assignments_for(session, game.id) if a.player_id == player_id)
    name = render.Names(session).cname(a.played_champion_id)
    return Answer({"type": MESSAGE, "data": render.reply(f"Locked in: **{name}**.", private=True)}, commit=True)


def _set_role(session: Session, game: ChallengeGame, player_id: int, role: str) -> Answer:
    rules.set_role(session, game, player_id, None if role == "auto" else role)
    text = "Role set back to auto: it comes from the game." if role == "auto" else f"Role set to **{render.ROLE_NAMES[role]}**. Your build follows it."
    return Answer({"type": MESSAGE, "data": render.reply(text, private=True)}, commit=True)


def _build_answer(session: Session, champion_id: str | None, role: str | None, private: bool) -> Answer:
    champ = session.get(Champion, champion_id) if champion_id else None
    if champ is None:
        raise Denied("Pick a champion from the list.")
    version = champ.ddragon_version

    async def followup(new_session: Callable[[], Session]) -> dict:
        static = None
        if version:
            try:
                static = await meta.load_static(version)
            except Exception:  # noqa: BLE001 - names and icons are optional
                static = None
        with new_session() as s:
            c = s.get(Champion, champ.id)
            pick = meta.suggest_comp(s, [c.id], static, roles={c.id: role} if role else None)["picks"][0]
            return render.build(pick, c)

    return Answer({"type": DEFER, "data": {"flags": render.EPHEMERAL} if private else {}}, followup=followup)


# --- buttons and menus --------------------------------------------------------------------------------


def _component(session: Session, who: Who, data: dict) -> Answer:
    custom = data["data"]["custom_id"].split(":")
    if custom[0] != "hd":
        return _say("That button is from an older message.")
    action, args = custom[1], custom[2:]
    ctx = _need_member(who)

    if action in ("ready", "unready"):
        run = session.get(Run, int(args[0]))
        if run is None or run.group_id != who.link.group_id:
            raise Denied("That ready check is for another group.")
        if ctx.player_id is None:
            raise Denied("Your account doesn't play as anyone in this group.")
        message = data.get("message") or {}
        row_ = session.get(DiscordMessage, (who.link.group_id, "ready", run.id))
        if row_ is None or row_.message_id != str(message.get("id")):
            if row_:
                session.delete(row_)
                session.flush()
            row_ = DiscordMessage(group_id=who.link.group_id, kind="ready", ref_id=run.id, channel_id=str(message.get("channel_id", "")), message_id=str(message.get("id", "")), data={"ready": []})
        ready = set(row_.data.get("ready", []))
        ready.add(ctx.player_id) if action == "ready" else ready.discard(ctx.player_id)
        row_.data = {"ready": sorted(ready)}
        row_.updated_at = utcnow()
        session.add(row_)
        settings = group_settings(session, who.link.group_id)
        players = list(settings.last_used_player_ids or []) or [p.id for p in session.exec(select(Player).where(Player.group_id == who.link.group_id)).all()]
        if ctx.player_id not in players:
            players.append(ctx.player_id)
        return Answer({"type": UPDATE, "data": render.ready_message(session, run, players, sorted(ready))}, commit=True)

    game = _game(session, who, int(args[0]))
    run = session.get(Run, game.run_id)
    if action == "result":
        _need_manager(ctx, run)
        rules.apply_result(session, game, args[1], source="manual")
        return Answer({"type": MESSAGE, "data": render.reply(f"Game {game.id}: {_RESULT_TEXT[game.status]}.", private=True)}, commit=True)
    if action == "undo":
        _need_manager(ctx, run)
        rules.undo_result(session, game)
        return Answer({"type": MESSAGE, "data": render.reply(f"Undid game {game.id}'s result.", private=True)}, commit=True)

    if action in ("use", "swap"):
        item = session.get(InventoryItem, int(args[1]))
        if item is None or item.run_id != run.id or not can_act_for(ctx, run, item.player_id):
            raise Denied("That item isn't yours.")
        payload: dict = {"game_id": game.id}
        if action == "swap":
            payload["other_player_id"] = int((data["data"].get("values") or ["0"])[0])
        shop.use_item(session, item, payload)
        n = render.Names(session)
        now = next(a for a in rules.assignments_for(session, game.id) if a.player_id == item.player_id)
        verb = "Rerolled" if item.type == "reroll" else f"Swapped with {n.pname(payload.get('other_player_id'))}"
        return Answer(
            {"type": MESSAGE, "data": render.reply(f"{verb}. Your options: {', '.join(n.cname(c) for c in now.options)}.", private=True)},
            commit=True,
        )

    # The rest act on the clicker's own spot in this spin.
    mine = next((a for a in rules.assignments_for(session, game.id) if a.player_id == ctx.player_id), None)
    if mine is None:
        if can_manage(ctx, run) and action == "role":
            raise Denied("You're not in this spin. To set someone else's role, use `/role` with their name.")
        raise Denied("You're not in this spin.")
    if action == "role":
        return _set_role(session, game, mine.player_id, (data["data"].get("values") or ["auto"])[0])
    if action == "build":
        cid = mine.played_champion_id or (mine.options[0] if mine.options else None)
        real = render._roles(session, game).get(mine.player_id)
        return _build_answer(session, cid, real["role"] if real else None, private=True)
    if action == "items":
        return _items_menu(session, game, mine.player_id)
    raise Denied("That button is from an older message.")


def _items_menu(session: Session, game: ChallengeGame, player_id: int) -> Answer:
    """The clicker's spin items (Reroll, Swap) as buttons, only for them."""
    items = session.exec(
        select(InventoryItem).where(
            InventoryItem.run_id == game.run_id,
            InventoryItem.player_id == player_id,
            InventoryItem.status == "unused",
            col(InventoryItem.type).in_(["reroll", "swap", "choose"]),
        )
    ).all()
    if not items:
        return _say("You have no Reroll, Swap or Choose a Champ. `/shop` to buy one.")
    n = render.Names(session)
    rows = []
    reroll = next((i for i in items if i.type == "reroll"), None)
    if reroll:
        rows.append(render.row(render.button(f"Reroll ({sum(i.type == 'reroll' for i in items)})", f"hd:use:{game.id}:{reroll.id}", style=1)))
    swap = next((i for i in items if i.type == "swap"), None)
    if swap:
        others = [a for a in rules.assignments_for(session, game.id) if a.player_id != player_id and not a.played_champion_id]
        if others:
            rows.append(
                render.row(
                    {
                        "type": 3,
                        "custom_id": f"hd:swap:{game.id}:{swap.id}",
                        "placeholder": "Swap your list with...",
                        "options": [{"label": n.pname(a.player_id), "value": str(a.player_id)} for a in others][:25],
                    }
                )
            )
    text = "Your items for this spin:"
    if any(i.type == "choose" for i in items):
        text += " (Choose a Champ needs a champion picked from the whole pool: use it on the site.)"
    return Answer({"type": MESSAGE, "data": render.reply(text, components=rows, private=True)})


# --- announcements: from the outbox to the group's channel ---------------------------------------------


def _announcing(link: DiscordLink | None, kind: str) -> bool:
    return bool(link and link.channel_id and kind not in (link.muted or []))


@dataclass
class _Post:
    group_id: int
    channel_id: str
    message: dict
    event_ids: list[int] = field(default_factory=list)
    kind: str | None = None  # kept as a DiscordMessage to edit later; None: a one-off post
    ref_id: int | None = None
    message_id: str | None = None  # edit this message instead of posting
    data: dict | None = None
    announce: list[str] = field(default_factory=list)  # trophies to record once posted


def _unlock_keys(session: Session, group_id: int) -> set[str]:
    from app.services.stats import group_player_ids

    pids = set(group_player_ids(session, group_id))
    return {f"{pid}:{aid}" for pid, unlocks in achievements.evaluate(session).items() if pid in pids for aid in unlocks}


def seed_announced(session: Session, link: DiscordLink) -> None:
    """A newly linked server starts from the trophies already earned (no flood of old ones)."""
    link.announced = sorted(_unlock_keys(session, link.group_id))


_RENDER = {"spin": render.spin_message, "result": render.result_message, "live": render.live_message}
# Which posts each event leads to: (switch, message kind, only edit an existing message).
_WANTED = {
    "spin": [("spins", "spin", False)],
    "picks": [("spins", "spin", False)],
    "game_found": [("live", "live", False)],
    "result": [("spins", "spin", True), ("results", "result", False)],
    "gold": [("results", "result", True)],
    "undo": [("spins", "spin", True), ("results", "result", True)],
}


def _plan(session: Session, events: list[EventOutbox]) -> tuple[list[_Post], set[int]]:
    """What to post or edit for a batch of events, and the events with nothing to post."""
    posts: list[_Post] = []
    planned: dict[tuple, _Post] = {}
    skipped: set[int] = set()
    trophies: dict[int, list[int]] = {}
    links: dict[int, DiscordLink | None] = {}

    for ev in events:
        if ev.group_id not in links:
            links[ev.group_id] = session.exec(select(DiscordLink).where(DiscordLink.group_id == ev.group_id)).first()
        link = links[ev.group_id]
        game = session.get(ChallengeGame, ev.payload["game_id"]) if ev.payload.get("game_id") else None
        used = False
        for switch, kind, edit_only in _WANTED.get(ev.type, []) if game is not None else []:
            if not _announcing(link, switch):
                continue
            key = (ev.group_id, kind, game.id)
            if key in planned:
                planned[key].event_ids.append(ev.id)
                used = True
                continue
            existing = session.get(DiscordMessage, key)
            if edit_only and existing is None:
                continue
            post = _Post(
                group_id=ev.group_id,
                channel_id=existing.channel_id if existing else link.channel_id,
                message=_RENDER[kind](session, game),
                event_ids=[ev.id],
                kind=kind,
                ref_id=game.id,
                message_id=existing.message_id if existing else None,
            )
            planned[key] = post
            posts.append(post)
            used = True
        if ev.type in ("result", "gold") and _announcing(link, "moments"):
            trophies.setdefault(ev.group_id, []).append(ev.id)
            used = True
        if ev.type == "revive" and _announcing(link, "moments"):
            msg = render.revive_message(session, ev.payload["run_id"], ev.payload["champion_id"], ev.payload.get("player_id"))
            posts.append(_Post(ev.group_id, link.channel_id, msg, [ev.id]))
            used = True
        if ev.type == "run_end" and _announcing(link, "recaps"):
            run = session.get(Run, ev.payload["run_id"])
            if run is not None:
                posts.append(_Post(ev.group_id, link.channel_id, render.run_end_message(session, run), [ev.id]))
                used = True
        if not used:
            skipped.add(ev.id)

    for group_id, event_ids in trophies.items():
        link = links[group_id]
        new = sorted(_unlock_keys(session, group_id) - set(link.announced or []))
        if new:
            unlocks = [(int(k.split(":")[0]), k.split(":", 1)[1]) for k in new]
            posts.append(_Post(group_id, link.channel_id, render.trophies_message(session, unlocks), list(event_ids), announce=new))
        else:
            # Nothing new: those events only needed their other posts (or none).
            for eid in event_ids:
                if not any(eid in p.event_ids for p in posts):
                    skipped.add(eid)
    return posts, skipped


async def _deliver(client, posts: list[_Post]) -> dict[int, str | DiscordError]:
    """Post or edit each message, with no database transaction open. Returns id(post) -> the
    message id, or the error."""
    out: dict[int, str | DiscordError] = {}
    for post in posts:
        try:
            if post.message_id:
                try:
                    await client.edit(post.channel_id, post.message_id, post.message)
                    out[id(post)] = post.message_id
                    continue
                except DiscordError as e:
                    if e.status != 404:
                        raise
                    # Someone deleted the message: post a fresh one.
            out[id(post)] = await client.post(post.channel_id, post.message)
        except DiscordError as e:
            out[id(post)] = e
        except Exception as e:  # noqa: BLE001 - a network blip; try again next time
            out[id(post)] = DiscordError(0, str(e))
    return out


def _record(session: Session, posts: list[_Post], results: dict[int, str | DiscordError]) -> None:
    now = utcnow()
    failed: dict[int, str] = {}
    done: set[int] = set()
    for post in posts:
        result = results.get(id(post))
        link = session.exec(select(DiscordLink).where(DiscordLink.group_id == post.group_id)).first()
        if result is None or isinstance(result, DiscordError):
            text = str(result) if result else "not sent"
            for eid in post.event_ids:
                failed[eid] = text
            if link is not None and isinstance(result, DiscordError) and result.lost_access:
                link.last_error = f"{now:%Y-%m-%d %H:%M} UTC: {text}"
                session.add(link)
            continue
        done.update(post.event_ids)
        if link is not None and link.last_error:
            link.last_error = None
            session.add(link)
        if post.kind:
            row_ = session.get(DiscordMessage, (post.group_id, post.kind, post.ref_id))
            if row_ is None:
                row_ = DiscordMessage(group_id=post.group_id, kind=post.kind, ref_id=post.ref_id, channel_id=post.channel_id, message_id=result)
            row_.message_id = result
            row_.updated_at = now
            if post.data is not None:
                row_.data = post.data
            session.add(row_)
        if post.announce and link is not None:
            link.announced = sorted(set(link.announced or []) | set(post.announce))
            session.add(link)
    for eid in done | set(failed):
        ev = session.get(EventOutbox, eid)
        if ev is None:
            continue
        if eid in failed:
            ev.attempts += 1
            ev.error = failed[eid][:500]
            if ev.attempts >= MAX_ATTEMPTS:
                ev.sent_at = now  # give up; the error stays on the row
        else:
            ev.sent_at = now
            ev.error = None
        session.add(ev)


async def _send(new_session: Callable[[], Session], client, posts: list[_Post]) -> None:
    if not posts:
        return
    results = await _deliver(client, posts)
    with new_session() as session:
        _record(session, posts, results)
        session.commit()


async def send_outbox(new_session: Callable[[], Session], client, limit: int = 50) -> int:
    """Send what the outbox has waiting. Returns how many events were handled."""
    with new_session() as session:
        events = session.exec(
            select(EventOutbox)
            .where(col(EventOutbox.sent_at).is_(None), EventOutbox.attempts < MAX_ATTEMPTS)
            .order_by(col(EventOutbox.id))
            .limit(limit)
        ).all()
        if not events:
            return 0
        posts, skipped = _plan(session, events)
        now = utcnow()
        for ev in events:
            if ev.id in skipped:
                ev.sent_at = now
                session.add(ev)
        session.commit()
        count = len(events)
    await _send(new_session, client, posts)
    return count


async def refresh_live(new_session: Callable[[], Session], client, static: dict | None = None) -> int:
    """Edit each live scoreboard when it changed, at most every LIVE_EDIT_SECONDS."""
    now = utcnow()
    posts = []
    with new_session() as session:
        rows = session.exec(
            select(DiscordMessage).where(DiscordMessage.kind == "live", DiscordMessage.updated_at > now - timedelta(hours=6))
        ).all()
        for r in rows:
            link = session.exec(select(DiscordLink).where(DiscordLink.group_id == r.group_id)).first()
            game = session.get(ChallengeGame, r.ref_id)
            if game is None or not _announcing(link, "live") or (now - r.updated_at).total_seconds() < LIVE_EDIT_SECONDS:
                continue
            msg = render.live_message(session, game, static)
            digest = hashlib.sha256(json.dumps(msg, sort_keys=True, default=str).encode()).hexdigest()
            if digest == r.data.get("digest"):
                continue
            posts.append(_Post(r.group_id, r.channel_id, msg, kind="live", ref_id=r.ref_id, message_id=r.message_id, data={"digest": digest}))
        session.commit()
    await _send(new_session, client, posts)
    return len(posts)


async def post_nudges(new_session: Callable[[], Session], client) -> int:
    """Once per game: a pending game that has waited NUDGE_AFTER with no result."""
    now = utcnow()
    posts = []
    with new_session() as session:
        for link in session.exec(select(DiscordLink)).all():
            if not _announcing(link, "nudges"):
                continue
            run = _active_run(session, link.group_id)
            game = rules.pending_game(session, run.id) if run and run.status == "active" else None
            if game is None or now - game.created_at < NUDGE_AFTER or session.get(DiscordMessage, (link.group_id, "nudge", game.id)):
                continue
            hours = int((now - game.created_at).total_seconds() // 3600)
            posts.append(_Post(link.group_id, link.channel_id, render.nudge_message(game, hours), kind="nudge", ref_id=game.id))
        session.commit()
    await _send(new_session, client, posts)
    return len(posts)


def last_month(today: datetime) -> str:
    prev = today.replace(day=1) - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


async def post_wrapped(new_session: Callable[[], Session], client, today: datetime | None = None) -> int:
    """Early each month: last month's Wrapped, once per server."""
    today = today or datetime.now(UTC)
    if today.day > 3:
        return 0
    month = last_month(today)
    posts = []
    with new_session() as session:
        for link in session.exec(select(DiscordLink)).all():
            if not _announcing(link, "recaps") or (link.state or {}).get("wrapped") == month:
                continue
            msg = render.wrapped_message(session, link.group_id, month)
            if msg is None:  # no games that month: nothing to post, and no need to check again
                link.state = {**(link.state or {}), "wrapped": month}
                session.add(link)
                continue
            posts.append(_Post(link.group_id, link.channel_id, msg))
        session.commit()
    if not posts:
        return 0
    results = await _deliver(client, posts)
    with new_session() as session:
        _record(session, posts, results)
        for post in posts:
            if not isinstance(results.get(id(post)), DiscordError):
                link = session.exec(select(DiscordLink).where(DiscordLink.group_id == post.group_id)).first()
                link.state = {**(link.state or {}), "wrapped": month}
                session.add(link)
        session.commit()
    return len(posts)


def prune_outbox(session: Session, keep_days: int = 14) -> None:
    """Old events aren't needed once handled (or when nobody is sending them)."""
    cutoff = utcnow() - timedelta(days=keep_days)
    for ev in session.exec(select(EventOutbox).where(EventOutbox.created_at < cutoff)).all():
        session.delete(ev)
