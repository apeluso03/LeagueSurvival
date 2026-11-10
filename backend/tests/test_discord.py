"""The Discord bot (SPEC 19): signatures, commands and buttons with the site's permissions, the
outbox sender, and linking servers and accounts."""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from nacl.signing import SigningKey
from sqlmodel import Session, select

from app.config import get_settings
from app.models import (
    AppSettings,
    ChallengeGame,
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
)
from app.services import discord_bot, rules
from app.services.discord_api import EPHEMERAL, DiscordError
from tests.conftest import GROUP, make_user
from tests.factories import FakeDiscord


@pytest.fixture
def key(monkeypatch) -> SigningKey:
    """The bot switched on, with a signing key standing in for Discord's."""
    k = SigningKey.generate()
    s = get_settings()
    for name, value in {
        "discord_app_id": "app-1",
        "discord_public_key": k.verify_key.encode().hex(),
        "discord_bot_token": "bot-token",
        "discord_client_secret": "client-secret",
        "public_url": "https://hd.test",
    }.items():
        monkeypatch.setattr(s, name, value)
    return k


@pytest.fixture
def fake(key, anon_client):
    from app.main import app
    from app.routers.discord import get_discord_client

    f = FakeDiscord()
    app.dependency_overrides[get_discord_client] = lambda: f
    return f


@pytest.fixture
def world(session, owner):
    """Group 1 linked to server g1 (channel c1). The owner plays as Alex (player 1) on Discord
    d-owner; Bea (player 2) is a member on d-bea. An active run."""
    m = session.exec(select(GroupMember).where(GroupMember.user_id == owner.id)).one()
    m.player_id = 1
    owner.discord_id = "d-owner"
    bea = make_user(session, "bea", player_id=2)
    bea.discord_id = "d-bea"
    run = rules.create_run(session, "Run", 3, group_id=GROUP)
    run.owner_user_id = owner.id
    settings = session.exec(select(AppSettings).where(AppSettings.group_id == GROUP)).one()
    settings.active_run_id = run.id
    link = DiscordLink(group_id=GROUP, guild_id="g1", guild_name="Friends", channel_id="c1")
    session.add_all([m, owner, bea, run, settings, link])
    session.commit()
    return SimpleNamespace(run=run, owner=owner, bea=bea, link=link)


def cmd(command: str, /, user: str = "d-owner", guild: str | None = "g1", **options) -> dict:
    return {
        "type": 2,
        "token": "tok",
        "guild_id": guild,
        "member": {"user": {"id": user}},
        "data": {"name": command, "options": [{"name": k, "value": v} for k, v in options.items()]},
    }


def click(custom_id: str, user: str = "d-owner", values=None, message=None) -> dict:
    data = {"custom_id": custom_id}
    if values is not None:
        data["values"] = values
    return {
        "type": 3,
        "token": "tok",
        "guild_id": "g1",
        "member": {"user": {"id": user}},
        "data": data,
        "message": message or {"id": "m-x", "channel_id": "c1"},
    }


def text(answer) -> str:
    return answer.response["data"]["content"]


def private(answer) -> bool:
    return bool(answer.response["data"].get("flags", 0) & EPHEMERAL)


def spin(session, world, players=(1, 2)) -> ChallengeGame:
    game = rules.create_spin(session, session.get(Run, world.run.id), list(players))
    session.commit()
    return game


def sender(engine):
    return lambda: Session(engine)


def send(engine, fake) -> int:
    return asyncio.run(discord_bot.send_outbox(sender(engine), fake))


# --- requests from Discord ---------------------------------------------------------------------


def signed(client, key: SigningKey, payload: dict, ts: int | None = None):
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()) if ts is None else ts)
    sig = key.sign(stamp.encode() + body).signature.hex()
    return client.post(
        "/api/discord/interactions",
        content=body,
        headers={"X-Signature-Ed25519": sig, "X-Signature-Timestamp": stamp, "Content-Type": "application/json"},
    )


def test_interactions_need_discords_signature(anon_client, fake, key):
    assert signed(anon_client, key, {"type": 1}).json() == {"type": 1}
    other = SigningKey.generate()
    assert signed(anon_client, other, {"type": 1}).status_code == 401
    assert signed(anon_client, key, {"type": 1}, ts=int(time.time()) - 3600).status_code == 401  # a replay
    bad = anon_client.post("/api/discord/interactions", content=b"{}", headers={"X-Signature-Ed25519": "zz", "X-Signature-Timestamp": "1"})
    assert bad.status_code == 401


def test_bot_off_means_no_endpoints(anon_client):
    assert anon_client.post("/api/discord/interactions", content=b"{}").status_code == 404
    assert anon_client.get("/api/discord/available").json() == {"enabled": False}


def test_command_over_http(anon_client, fake, key, world):
    r = signed(anon_client, key, cmd("run"))
    assert r.status_code == 200
    embed = r.json()["data"]["embeds"][0]
    assert embed["title"] == "Run" and "wins" in embed["description"] and embed["url"] == "https://hd.test/"


# --- who can do what ----------------------------------------------------------------------------


def test_servers_and_people_that_arent_linked(session, world, key):
    assert "isn't linked" in text(discord_bot.handle(session, cmd("run", guild="g-other")))
    assert "your group's Discord server" in text(discord_bot.handle(session, cmd("run", guild=None)))
    # Anyone in the linked server can look...
    assert discord_bot.handle(session, cmd("pool", user="d-stranger")).response["data"]["embeds"]
    # ...but must link their Discord to act.
    a = discord_bot.handle(session, cmd("gold", user="d-stranger"))
    assert private(a) and "Link your Discord account first" in text(a) and "https://hd.test/settings" in text(a)


def test_members_act_for_themselves_and_the_owner_runs_the_game(session, world):
    a = discord_bot.handle(session, cmd("spin", user="d-bea", player1="1", player2="2"))
    assert "Only the run's owner" in text(a)
    a = discord_bot.handle(session, cmd("spin", player1="1", player2="2"))
    assert "Spun for game" in text(a) and private(a) and "<#c1>" in text(a)
    game = rules.pending_game(session, world.run.id)
    assert game is not None
    assert "Only the run's owner" in text(discord_bot.handle(session, cmd("pick", user="d-bea", option=1)))
    assert "Only the run's owner" in text(discord_bot.handle(session, click(f"hd:result:{game.id}:win", user="d-bea")))
    # Bea sets her own role, not the owner's.
    a = discord_bot.handle(session, click(f"hd:role:{game.id}", user="d-bea", values=["JUNGLE"]))
    assert "Jungle" in text(a)
    assert "your own player" in text(discord_bot.handle(session, cmd("role", user="d-bea", role="TOP", player="1")))
    roles = {a.player_id: a.played_role for a in rules.assignments_for(session, game.id)}
    assert roles == {1: None, 2: "JUNGLE"}
    # The owner marks a pick, records the result, and undoes it.
    assert "Locked in" in text(discord_bot.handle(session, cmd("pick", option=2, player="2")))
    assert "win recorded" in text(discord_bot.handle(session, click(f"hd:result:{game.id}:win")))
    session.expire_all()
    assert session.get(ChallengeGame, game.id).status == "won"
    assert "Undid" in text(discord_bot.handle(session, cmd("undo")))
    session.expire_all()
    assert session.get(ChallengeGame, game.id).status == "pending"


def test_another_groups_game_and_players_are_off_limits(session, world):
    other = Group(name="Other")
    session.add(other)
    session.flush()
    stranger = Player(display_name="Zed", group_id=other.id)
    run = Run(group_id=other.id, name="Theirs")
    session.add_all([stranger, run])
    session.flush()
    game = ChallengeGame(run_id=run.id)
    session.add(game)
    session.commit()
    assert "another group" in text(discord_bot.handle(session, click(f"hd:result:{game.id}:win"))) or "isn't in this server's group" in text(
        discord_bot.handle(session, click(f"hd:result:{game.id}:win"))
    )
    choices = discord_bot.handle(session, {**cmd("stats"), "type": 4, "data": {"name": "stats", "options": [{"name": "player", "value": "", "focused": True}]}})
    names = [c["name"] for c in choices.response["data"]["choices"]]
    assert "Alex" in names and "Zed" not in names
    assert "no player" in text(discord_bot.handle(session, cmd("spin", player1="1", player2=str(stranger.id))))


def test_gold_and_shop_are_private(session, world):
    from app.services import economy

    economy.record(session, world.run.id, 2, 1000, "adjust")
    session.commit()
    a = discord_bot.handle(session, cmd("gold", user="d-bea"))
    assert private(a) and "1,000" in a.response["data"]["embeds"][0]["description"]
    a = discord_bot.handle(session, cmd("shop", user="d-bea", item="reroll"))
    assert private(a) and "Bought **Reroll**" in text(a)
    assert "your own player" in text(discord_bot.handle(session, cmd("shop", user="d-bea", item="reroll", player="1")))


def test_items_from_the_spin_message(session, world):
    from app.services import economy, shop

    economy.record(session, world.run.id, 2, 2000, "adjust")
    item, _ = shop.purchase(session, session.get(Run, world.run.id), 2, "reroll")
    session.commit()
    game = spin(session, world)
    a = discord_bot.handle(session, click(f"hd:items:{game.id}", user="d-bea"))
    assert private(a)
    button = a.response["data"]["components"][0]["components"][0]
    assert button["custom_id"] == f"hd:use:{game.id}:{item.id}"
    before = next(x.options for x in rules.assignments_for(session, game.id) if x.player_id == 2)
    assert "your item" in text(discord_bot.handle(session, click(button["custom_id"], user="d-stranger"))) or "Link" in text(
        discord_bot.handle(session, click(button["custom_id"], user="d-stranger"))
    )
    a = discord_bot.handle(session, click(button["custom_id"], user="d-bea"))
    assert "Rerolled" in text(a)
    session.expire_all()
    after = next(x.options for x in rules.assignments_for(session, game.id) if x.player_id == 2)
    assert after != before


def test_ready_check(session, world):
    a = discord_bot.handle(session, cmd("ready", user="d-bea"))
    assert "Ready check" in a.response["data"]["embeds"][0]["title"]
    a = discord_bot.handle(session, click(f"hd:ready:{world.run.id}", user="d-bea", message={"id": "m-ready", "channel_id": "c1"}))
    assert a.response["type"] == discord_bot.UPDATE
    assert "✅ Bea" in a.response["data"]["embeds"][0]["description"]
    a = discord_bot.handle(session, click(f"hd:ready:{world.run.id}", message={"id": "m-ready", "channel_id": "c1"}))
    assert "✅ Alex" in a.response["data"]["embeds"][0]["description"]
    a = discord_bot.handle(session, click(f"hd:unready:{world.run.id}", user="d-bea", message={"id": "m-ready", "channel_id": "c1"}))
    assert "⬜ Bea" in a.response["data"]["embeds"][0]["description"]


def test_new_run_is_for_the_group_owner(session, world):
    assert "group's owner" in text(discord_bot.handle(session, cmd("newrun", user="d-bea", name="Mine")))
    discord_bot.handle(session, cmd("newrun", name="Season 2", options=4))
    session.expire_all()
    settings = session.exec(select(AppSettings).where(AppSettings.group_id == GROUP)).one()
    run = session.get(Run, settings.active_run_id)
    assert run.name == "Season 2" and run.options_per_player == 4


def test_build_fills_in_after_thinking(session, world, engine):
    a = discord_bot.handle(session, cmd("build", champion="Champ001", role="JUNGLE"))
    assert a.response["type"] == discord_bot.DEFER and a.followup is not None
    msg = asyncio.run(a.followup(lambda: Session(engine)))
    assert msg["embeds"][0]["title"].startswith("Champ 1") and "mobalytics.gg/lol/champions/champ001" in msg["embeds"][0]["url"]


# --- announcements --------------------------------------------------------------------------------


def test_a_spin_is_one_message_edited_through_to_the_result(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    assert send(engine, fake) == 1
    assert len(fake.posts) == 1
    channel, msg = fake.posts[0]
    assert channel == "c1" and msg["embeds"][0]["title"] == f"Game {game.id} · Pick phase · 0/2 picked"
    assert [e["author"]["name"] for e in msg["embeds"][1:]] == ["Alex", "Bea"]
    assert any(c.get("custom_id") == f"hd:result:{game.id}:win" for r in msg["components"] for c in r["components"])

    rules.set_played(session, game, [rules.Pick(player_id=1, option_index=0), rules.Pick(player_id=2, option_index=1)])
    session.commit()
    send(engine, fake)
    assert len(fake.posts) == 1 and fake.edits[-1][1] == "m101"
    assert "Locked in" in fake.edits[-1][2]["embeds"][0]["title"]

    rules.apply_result(session, game, "loss")
    session.commit()
    send(engine, fake)
    # The spin message loses its buttons; the result is a new message.
    assert fake.edits[-1][1] == "m101" and fake.edits[-1][2]["components"] == []
    result = next(m["embeds"][0] for _, m in fake.posts[1:] if m["embeds"][0]["title"].startswith(f"Game {game.id} · "))
    assert result["title"] == f"Game {game.id} · Defeat" and any(f["name"] == "Eliminated" for f in result["fields"])

    rules.undo_result(session, game)
    session.commit()
    send(engine, fake)
    assert "undone" in fake.edits[-1][2]["embeds"][0]["title"]
    assert not session.exec(select(EventOutbox).where(EventOutbox.sent_at == None)).all()  # noqa: E711


def test_switched_off_announcements_are_skipped(session, world, engine):
    link = session.get(DiscordLink, world.link.id)
    link.muted = ["spins"]
    session.add(link)
    session.commit()
    fake = FakeDiscord()
    game = spin(session, world)
    send(engine, fake)
    assert fake.posts == []
    rules.apply_result(session, game, "win")
    session.commit()
    send(engine, fake)
    assert [m["embeds"][0]["title"] for _, m in fake.posts][0] == f"Game {game.id} · Victory"
    session.expire_all()
    assert all(e.sent_at for e in session.exec(select(EventOutbox)).all())


def test_groups_without_a_server_post_nothing(session, world, engine):
    session.delete(session.get(DiscordLink, world.link.id))
    session.commit()
    fake = FakeDiscord()
    spin(session, world)
    assert send(engine, fake) == 1 and fake.posts == []


def test_lost_access_is_retried_then_shown_in_settings(session, world, engine):
    fake = FakeDiscord()
    fake.fail["post"] = DiscordError(403, "Missing Access")
    spin(session, world)
    send(engine, fake)
    session.expire_all()
    ev = session.exec(select(EventOutbox)).one()
    assert ev.sent_at is None and ev.attempts == 1 and "Missing Access" in ev.error
    assert "Missing Access" in session.get(DiscordLink, world.link.id).last_error
    del fake.fail["post"]
    send(engine, fake)
    session.expire_all()
    assert len(fake.posts) == 1 and session.get(DiscordLink, world.link.id).last_error is None


def test_gives_up_after_max_attempts(session, world, engine):
    fake = FakeDiscord()
    fake.fail["post"] = DiscordError(500, "Discord is down")
    spin(session, world)
    for _ in range(discord_bot.MAX_ATTEMPTS):
        send(engine, fake)
    session.expire_all()
    ev = session.exec(select(EventOutbox)).one()
    assert ev.attempts == discord_bot.MAX_ATTEMPTS and ev.sent_at is not None and "down" in ev.error
    assert send(engine, fake) == 0


def test_a_deleted_message_is_posted_again(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    send(engine, fake)
    fake.fail["edit"] = DiscordError(404, "Unknown Message")
    rules.set_role(session, game, 1, "TOP")
    session.commit()
    send(engine, fake)
    assert len(fake.posts) == 2
    session.expire_all()
    assert session.get(DiscordMessage, (GROUP, "spin", game.id)).message_id == "m102"


def test_trophies_once_and_not_the_old_ones(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    rules.apply_result(session, game, "win")
    session.commit()
    send(engine, fake)
    titles = [m["embeds"][0]["title"] for _, m in fake.posts]
    assert "Trophies unlocked" in titles  # First Blood for both players
    trophies = next(m for _, m in fake.posts if m["embeds"][0]["title"] == "Trophies unlocked")
    assert "First Blood" in trophies["embeds"][0]["description"]
    session.expire_all()
    announced = session.get(DiscordLink, world.link.id).announced
    assert "1:first_win" in announced and "2:first_win" in announced
    # A server linked later starts from what's already earned.
    link = session.get(DiscordLink, world.link.id)
    link.announced = []
    discord_bot.seed_announced(session, link)
    assert "1:first_win" in link.announced


def test_revives_and_run_recaps(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    rules.set_played(session, game, [rules.Pick(player_id=1, option_index=0), rules.Pick(player_id=2, option_index=0)])
    rules.apply_result(session, game, "loss")
    session.commit()
    lost = rules.assignments_for(session, game.id)[0].played_champion_id
    from app.models import ReviveToken

    token = ReviveToken(run_id=world.run.id, player_id=1, earned_in_game_id=game.id)
    session.add(token)
    session.flush()
    rules.use_token(session, token, lost)
    rules.end_run(session, session.get(Run, world.run.id))
    session.commit()
    send(engine, fake)
    titles = [m["embeds"][0]["title"] for _, m in fake.posts]
    assert any(t.endswith("is back") for t in titles)
    assert "Run over · Run" in titles


def test_nudge_once_for_a_game_stuck_without_a_result(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    game.created_at = datetime.now(UTC) - timedelta(hours=4)
    session.add(game)
    session.commit()
    assert asyncio.run(discord_bot.post_nudges(sender(engine), fake)) == 1
    assert asyncio.run(discord_bot.post_nudges(sender(engine), fake)) == 0
    assert "still waiting" in fake.posts[0][1]["embeds"][0]["title"]


def test_wrapped_early_in_the_month_once(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    rules.apply_result(session, game, "win")
    session.commit()
    now = datetime.now(UTC)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=2)
    assert asyncio.run(discord_bot.post_wrapped(sender(engine), fake, today=next_month.replace(day=10))) == 0
    assert asyncio.run(discord_bot.post_wrapped(sender(engine), fake, today=next_month)) == 1
    assert asyncio.run(discord_bot.post_wrapped(sender(engine), fake, today=next_month)) == 0
    assert fake.posts[0][1]["embeds"][0]["title"].startswith("Wrapped · ")


def test_live_scoreboard_edits_only_when_it_changes(session, world, engine):
    from app.services import live

    fake = FakeDiscord()
    game = spin(session, world)
    send(engine, fake)  # the spin
    row = live._live_row(session, game)
    row.queue_id = 400
    row.participants = [{"champion_id": "Champ001", "team": 100, "spells": [4, 11], "keystone": None, "player_id": 1}]
    session.add(row)
    session.commit()
    send(engine, fake)
    live_post = fake.posts[-1][1]["embeds"][0]
    assert live_post["title"] == f"In game · Game {game.id} · Normal Draft" and "Alex" in live_post["description"]
    # Too soon to edit, then nothing changed, then it changed.
    assert asyncio.run(discord_bot.refresh_live(sender(engine), fake)) == 0
    msg = session.get(DiscordMessage, (GROUP, "live", game.id))
    msg.updated_at = datetime.now(UTC) - timedelta(minutes=5)
    session.add(msg)
    session.commit()
    assert asyncio.run(discord_bot.refresh_live(sender(engine), fake)) == 1  # first edit records a digest
    session.expire_all()
    msg = session.get(DiscordMessage, (GROUP, "live", game.id))
    msg.updated_at = datetime.now(UTC) - timedelta(minutes=5)
    session.add(msg)
    session.commit()
    assert asyncio.run(discord_bot.refresh_live(sender(engine), fake)) == 0
    row = session.get(LiveGame, game.id)
    row.ended_at = datetime.now(UTC)
    session.add(row)
    session.commit()
    assert asyncio.run(discord_bot.refresh_live(sender(engine), fake)) == 1
    assert fake.edits[-1][2]["embeds"][0]["title"].startswith("Game over")


# --- Settings: linking a server and accounts ---------------------------------------------------------


def oauth(client, path: str):
    """Start an OAuth flow; returns Discord's consent URL and the state it carries."""
    from urllib.parse import parse_qs, urlparse

    r = client.get(path, follow_redirects=False)
    assert r.status_code == 302, r.text
    url = r.headers["location"]
    return url, parse_qs(urlparse(url).query)["state"][0]


def test_add_the_bot_to_a_server(client, session, fake, owner):
    url, state = oauth(client, "/api/discord/install")
    assert url.startswith("https://discord.com/oauth2/authorize") and "bot+applications.commands" in url
    fake.token = {"access_token": "at", "scope": "bot applications.commands identify", "guild": {"id": "g9", "name": "Den", "system_channel_id": "c-sys"}}
    r = client.get(f"/api/discord/callback?code=abc&state={state}&guild_id=g9", follow_redirects=False)
    assert r.headers["location"] == "/settings?discord=server#discord"
    session.expire_all()
    link = session.exec(select(DiscordLink).where(DiscordLink.group_id == GROUP)).one()
    assert (link.guild_id, link.guild_name, link.channel_id) == ("g9", "Den", "c-sys")
    assert session.get(User, owner.id).discord_id == "d-owner"  # the owner's Discord came along

    out = client.get("/api/discord").json()
    assert out["enabled"] and out["linked"] and out["server"]["guild_name"] == "Den"
    assert client.get("/api/discord/channels").json() == [{"id": "c1", "name": "general", "position": 0}]
    assert client.patch("/api/discord/server", json={"channel_id": "nope"}).status_code == 422
    assert client.patch("/api/discord/server", json={"channel_id": "c1", "muted": ["nudges"]}).json()["server"]["channel_id"] == "c1"
    assert client.post("/api/discord/test").status_code == 204 and fake.posts[-1][0] == "c1"
    assert client.delete("/api/discord/server").status_code == 204 and fake.left == ["g9"]
    assert client.get("/api/discord").json()["server"] is None


def test_oauth_state_is_tied_to_the_browser(client, session, fake, anon_client):
    _, state = oauth(client, "/api/discord/install")
    # Someone else's browser (no cookie) can't finish it.
    r = anon_client.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert "discord_error=expired" in r.headers["location"]
    r = client.get(f"/api/discord/callback?code=abc&state={state[:-2]}xx", follow_redirects=False)
    assert "discord_error=expired" in r.headers["location"]
    assert session.exec(select(DiscordLink)).first() is None


def test_one_server_per_group(client, session, fake, owner):
    other = Group(name="Other")
    session.add(other)
    session.flush()
    session.add(DiscordLink(group_id=other.id, guild_id="g9"))
    session.commit()
    _, state = oauth(client, "/api/discord/install")
    fake.token = {"access_token": "at", "scope": "bot identify", "guild": {"id": "g9", "name": "Den"}}
    r = client.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert "discord_error=server-taken" in r.headers["location"]


def test_only_the_group_owner_adds_the_bot(session, sign_in, fake):
    bea = sign_in(make_user(session, "bea", player_id=2))
    assert bea.get("/api/discord/install", follow_redirects=False).status_code == 403
    assert bea.get("/api/discord/channels").status_code == 403


def test_link_a_discord_account_and_sign_in_with_it(session, sign_in, fake, anon_client):
    bea_user = make_user(session, "bea", player_id=2)
    bea = sign_in(bea_user)
    url, state = oauth(bea, "/api/discord/connect")
    assert "scope=identify" in url
    fake.user = {"id": "d-bea"}
    r = bea.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert r.headers["location"] == "/settings?discord=linked#discord"
    session.expire_all()
    assert session.get(User, bea_user.id).discord_id == "d-bea"

    # Sign in with it from a signed-out browser.
    _, state = oauth(anon_client, "/api/discord/login")
    r = anon_client.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False)
    assert r.headers["location"] == "/" and "lst_session" in r.headers.get("set-cookie", "")
    assert anon_client.get("/api/auth/me").json()["user"]["username"] == "bea"

    # A Discord account nobody linked can't sign in; one already linked can't be linked twice.
    anon_client.cookies.clear()
    fake.user = {"id": "d-nobody"}
    _, state = oauth(anon_client, "/api/discord/login")
    assert "not-linked" in anon_client.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False).headers["location"]
    cal = sign_in(make_user(session, "cal", player_id=3))
    fake.user = {"id": "d-bea"}
    _, state = oauth(cal, "/api/discord/connect")
    assert "discord_error=taken" in cal.get(f"/api/discord/callback?code=abc&state={state}", follow_redirects=False).headers["location"]

    assert bea.delete("/api/discord/account").status_code == 204
    session.expire_all()
    assert session.get(User, bea_user.id).discord_id is None


def test_commands_are_valid_for_discord():
    for c in discord_bot.COMMANDS:
        assert 1 <= len(c["description"]) <= 100 and c["name"].islower()
        required = [o["required"] for o in c.get("options", [])]
        assert required == sorted(required, reverse=True), c["name"]  # required options first


def test_job_registers_commands_and_sends(engine, session, world, key, monkeypatch):
    from app.jobs import discord_bot as job

    fake = FakeDiscord()
    spin(session, world)

    async def stop(_):
        raise asyncio.CancelledError

    monkeypatch.setattr(job.asyncio, "sleep", stop)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(job.run_forever(engine, client_factory=lambda: fake))
    assert fake.commands == discord_bot.COMMANDS and len(fake.posts) == 1
