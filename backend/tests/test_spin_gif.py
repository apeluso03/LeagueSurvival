"""The spin reels as a GIF for Discord: drawing it, posting it before the draft, and /spin."""

import asyncio
import io
import random

from PIL import Image
from sqlmodel import Session, select

from app.models import DiscordLink
from app.services import discord_bot, rules, spin_gif
from tests.factories import FakeDiscord
from tests.test_discord import cmd, key, send, signed, spin, world  # noqa: F401 - fixtures


def test_strip_puts_the_options_around_the_landing_card():
    rng = random.Random(1)
    strip = spin_gif.build_strip([f"F{i}" for i in range(20)], ["A", "B", "C"], rng)
    f = spin_gif.FINAL_INDEX
    assert len(strip) == spin_gif.STRIP_LENGTH
    assert (strip[f], strip[f - 1], strip[f + 1]) == ("A", "B", "C")
    assert all(a != b for a, b in zip(strip, strip[1:], strict=False))  # never the same card twice in a row


def test_plan_and_draw(session, world):
    game = spin(session, world, players=(1, 2, 3))
    spec = spin_gif.plan(session, game, random.Random(2))
    assert [r["player"] for r in spec["rows"]] == ["Alex", "Bea", "Cal"]
    assert spec["seconds"] == spin_gif.SPIN_S + 2 * spin_gif.STAGGER_S
    for row, a in zip(spec["rows"], rules.assignments_for(session, game.id), strict=True):
        assert row["strip"][spin_gif.FINAL_INDEX] == a.options[0]
    gif = asyncio.run(spin_gif.render(spec))
    im = Image.open(io.BytesIO(gif))
    assert im.format == "GIF" and im.size == (spin_gif.W, spin_gif.TOP * 2 + spin_gif.ROW_H * 3)
    assert im.n_frames > 20 and len(gif) < 8_000_000


def test_a_new_spin_posts_its_reels_before_the_draft(session, world, engine):
    fake = FakeDiscord()
    game = spin(session, world)
    send(engine, fake)
    assert len(fake.reels) == 1 and len(fake.posts) == 1
    channel, intro, name, data = fake.reels[0]
    assert channel == "c1" and name == "spin.gif" and data[:6] == b"GIF89a"
    assert intro["content"] == f"🎰 **Game {game.id}**: spinning for Alex and Bea..."
    # Picks edit the draft; the reels aren't posted again.
    rules.set_played(session, game, [rules.Pick(player_id=1, option_index=0)])
    session.commit()
    send(engine, fake)
    assert len(fake.reels) == 1 and len(fake.posts) == 1 and fake.edits


def test_the_draft_still_goes_out_if_the_reels_cant_be_drawn(session, world, engine, monkeypatch):
    async def broken(spec, http=None):
        raise RuntimeError("no fonts")

    monkeypatch.setattr(spin_gif, "render", broken)
    fake = FakeDiscord()
    spin(session, world)
    send(engine, fake)
    assert fake.reels == [] and len(fake.posts) == 1


def test_spin_command_without_a_channel_answers_with_the_reels(session, world, engine):
    link = session.exec(select(DiscordLink)).one()
    link.channel_id = None
    session.add(link)
    session.commit()
    a = discord_bot.handle(session, cmd("spin", player1="1", player2="2"))
    assert a.response["type"] == discord_bot.DEFER and a.followup is not None
    msg = asyncio.run(a.followup(lambda: Session(engine)))
    assert msg["content"].startswith("🎰 **Game") and msg["_files"][0][0] == "spin.gif"
    (wait, draft), = msg["_then"]
    assert wait == 0 and "Pick phase" in draft["embeds"][0]["title"]


def test_spin_reply_goes_through_the_endpoint(session, world, key, anon_client):  # noqa: F811
    from app.main import app
    from app.routers.discord import get_discord_client

    link = session.exec(select(DiscordLink)).one()
    link.channel_id = None
    session.add(link)
    session.commit()
    fake = FakeDiscord()
    app.dependency_overrides[get_discord_client] = lambda: fake
    res = signed(anon_client, key, cmd("spin", player1="1", player2="2"))
    assert res.json()["type"] == discord_bot.DEFER
    # The background task filled in the reply with the GIF, then posted the draft under it.
    assert [n for _, n, _ in fake.reply_files] == ["spin.gif"] and "_files" not in fake.replies[0][1]
    assert "Pick phase" in fake.followups[0][1]["embeds"][0]["title"]
