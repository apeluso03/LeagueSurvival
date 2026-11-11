"""The spin reels as an animated GIF for Discord (SPEC 19.5, 21.3).

The same case-opening reels as the Wheels tab (frontend/src/lib/reel.ts): one row per player, a
strip of champion portraits that slows down (ease-out quart) and stops with option #1 under the
marker and the backups beside it, each row a little after the one above.

`plan` reads the database and returns a plain spec (portrait URLs, names, colours, landing spots);
`render` fetches the portraits and draws the frames off the event loop. Kept small for Discord:
about 1 to 2 MB for five players.
"""

import asyncio
import io
import logging
import random
from collections import OrderedDict

import httpx
from PIL import Image, ImageDraw, ImageFont
from sqlmodel import Session, col, select

from app.models import ChallengeGame, Champion, Player
from app.services import rules

log = logging.getLogger("uvicorn.error")

FILENAME = "spin.gif"
STRIP_LENGTH = 30
FINAL_INDEX = 24  # the card that lands under the marker (option #1)
OPTION_OFFSETS = [0, -1, 1, -2]  # #1 on the marker, #2 left, #3 right, #4 two left (as on the site)
FILLERS = 24  # random alive champions to fill the strips with (fewer portraits to fetch)

W = 520
LABEL_W = 108
CARD = 60
GAP = 6
STRIDE = CARD + GAP
ROW_H = 98
TOP = 10
FPS = 10
SPIN_S = 3.4  # the first row's spin; each next row stops STAGGER_S later
STAGGER_S = 0.35
HOLD_MS = 6000  # the last frame stays this long (the GIF plays once)

BG = (13, 17, 24)
WELL = (6, 8, 12)
GOLD = (232, 201, 122)
TEXT = (232, 237, 245)
MUTED = (133, 144, 163)
TEAM_COLORS = ["#2e9bff", "#ff4655", "#f0b232", "#a970ff", "#2fd27a", "#ff8a1f", "#19d3e6", "#ff5fb4"]
CLASS_COLORS = {
    "Assassin": "#e0434f",
    "Mage": "#8b5cf6",
    "Fighter": "#e8823a",
    "Tank": "#4fae6b",
    "Marksman": "#e3c04d",
    "Support": "#2e9bff",
}


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def team_color(player: Player) -> str:
    if player.color and player.color.startswith("#") and len(player.color) == 7:
        return player.color
    return TEAM_COLORS[((player.id or 1) - 1) % len(TEAM_COLORS)]


def build_strip(fillers: list[str], options: list[str], rng: random.Random) -> list[str]:
    """Like the site's buildStrip: options around the landing card, random fillers elsewhere that
    never repeat back to back or show an option near the landing spot."""
    placed = {FINAL_INDEX + d: o for d, o in zip(OPTION_OFFSETS, options, strict=False)}
    pool = fillers if len(fillers) > 1 else list(options[:1])
    strip: list[str] = []
    for i in range(STRIP_LENGTH):
        if i in placed:
            strip.append(placed[i])
            continue
        pick = rng.choice(pool)
        for _ in range(20):
            near = abs(i - FINAL_INDEX) <= 4 and pick in options
            if len(pool) <= 2 or not (pick == (strip[-1] if strip else None) or pick == placed.get(i + 1) or near):
                break
            pick = rng.choice(pool)
        strip.append(pick)
    return strip


def plan(session: Session, game: ChallengeGame, rng: random.Random | None = None) -> dict | None:
    """Everything the GIF needs, as plain data (so drawing can happen with no session open)."""
    rng = rng or random.Random()
    assignments = [a for a in rules.assignments_for(session, game.id) if a.options]
    if not assignments:
        return None
    alive = rules.alive_champion_ids(session, game.run_id)
    fillers = rng.sample(alive, min(FILLERS, len(alive))) if alive else []
    if len(fillers) < 2:
        fillers = sorted({c for a in assignments for c in a.options})
    wanted = set(fillers) | {c for a in assignments for c in a.options}
    champs = {c.id: c for c in session.exec(select(Champion).where(col(Champion.id).in_(wanted))).all()}
    cards = {
        cid: {"image": c.image_url, "name": c.name, "color": CLASS_COLORS.get((c.tags or [""])[0], "#5b5a56")}
        for cid, c in champs.items()
    }
    rows = []
    for a in assignments:
        player = session.get(Player, a.player_id)
        rows.append(
            {
                "player": player.display_name if player else f"Player {a.player_id}",
                "color": team_color(player) if player else TEAM_COLORS[0],
                "strip": build_strip(fillers, a.options, rng),
                "options": a.options[: len(OPTION_OFFSETS)],
                "offset": (rng.random() - 0.5) * CARD * 0.6,  # where inside the card it stops
            }
        )
    return {"game_id": game.id, "cards": cards, "rows": rows, "seconds": seconds(len(rows))}


def seconds(rows: int) -> float:
    """How long the reels run before the last row stops."""
    return SPIN_S + max(0, rows - 1) * STAGGER_S


# --- portraits -------------------------------------------------------------------------------

_icons: OrderedDict[str, Image.Image] = OrderedDict()
_ICON_CACHE = 400


async def _fetch_icons(urls: set[str], http: httpx.AsyncClient | None = None) -> dict[str, Image.Image]:
    """Portraits by URL (Data Dragon), kept in memory. Missing ones are left out (drawn as blanks)."""
    out = {u: _icons[u] for u in urls if u in _icons}
    todo = [u for u in urls if u and u not in out]
    if not todo:
        return out
    own = http is None
    http = http or httpx.AsyncClient(timeout=10)
    sem = asyncio.Semaphore(8)

    async def one(url: str) -> None:
        async with sem:
            try:
                res = await http.get(url)
                res.raise_for_status()
                img = Image.open(io.BytesIO(res.content)).convert("RGB").resize((CARD, CARD), Image.LANCZOS)
            except Exception as e:  # noqa: BLE001 - a blank card beats no GIF
                log.debug("No portrait from %s: %s", url, e)
                return
        out[url] = _icons[url] = img
        while len(_icons) > _ICON_CACHE:
            _icons.popitem(last=False)

    try:
        await asyncio.gather(*(one(u) for u in todo))
    finally:
        if own:
            await http.aclose()
    return out


# --- drawing ---------------------------------------------------------------------------------


def _ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 4


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow: no sizes
        return ImageFont.load_default()


def draw(spec: dict, icons: dict[str, Image.Image]) -> bytes:
    rows = spec["rows"]
    cards = spec["cards"]
    h = TOP * 2 + ROW_H * len(rows)
    win_x0, win_x1 = LABEL_W, W - 10
    marker = (win_x0 + win_x1) / 2
    name_font, small_font, num_font = _font(14), _font(12), _font(11)

    def tile(cid: str, lit: str | None) -> Image.Image:
        """One card: the portrait with its class colour along the bottom; lit = the option ring."""
        c = cards.get(cid, {})
        img = icons.get(c.get("image", ""))
        im = img.copy() if img is not None else Image.new("RGB", (CARD, CARD), (44, 51, 64))
        d = ImageDraw.Draw(im)
        if img is None:
            d.text((CARD / 2, CARD / 2), (c.get("name") or "?")[:2], fill=MUTED, font=name_font, anchor="mm")
        d.rectangle([0, CARD - 4, CARD, CARD], fill=_hex(c.get("color", "#5b5a56")))
        if lit:
            d.rectangle([0, 0, CARD - 1, CARD - 1], outline=_hex(lit) if lit.startswith("#") else GOLD, width=3)
        return im

    plain = {cid: tile(cid, None) for cid in cards}
    dim_cache: dict[str, Image.Image] = {}

    def dimmed(cid: str) -> Image.Image:
        if cid not in dim_cache:
            dim_cache[cid] = Image.blend(plain.get(cid) or tile(cid, None), Image.new("RGB", (CARD, CARD), WELL), 0.6)
        return dim_cache[cid]

    durations = [SPIN_S + i * STAGGER_S for i in range(len(rows))]
    total = max(durations)
    n_frames = int(total * FPS) + 1
    frames: list[Image.Image] = []
    for f in range(n_frames + 1):
        t_s = min(f / FPS, total)
        frame = Image.new("RGB", (W, h), BG)
        d = ImageDraw.Draw(frame)
        for r, row in enumerate(rows):
            y = TOP + r * ROW_H
            landed = t_s >= durations[r]
            # The player: a team-colour bar and their name.
            d.rectangle([10, y + 22, 14, y + 22 + CARD], fill=_hex(row["color"]))
            d.text((22, y + 22 + CARD / 2), row["player"][:12], fill=TEXT, font=name_font, anchor="lm")
            # The reel window.
            cy = y + 22
            d.rectangle([win_x0, cy - 4, win_x1, cy + CARD + 4], fill=WELL)
            start = CARD / 2
            end = FINAL_INDEX * STRIDE + CARD / 2 + row["offset"]
            pos = start + (end - start) * _ease(t_s / durations[r])
            # Card k's left edge sits at marker - pos + k * STRIDE.
            first = max(0, int((pos - (marker - win_x0)) // STRIDE) - 1)
            option_at = {FINAL_INDEX + dlt: i for i, dlt in enumerate(OPTION_OFFSETS[: len(row["options"])])}
            for k in range(first, min(STRIP_LENGTH, first + (win_x1 - win_x0) // STRIDE + 3)):
                x = int(round(marker - pos + k * STRIDE))
                if x + CARD < win_x0 or x > win_x1:
                    continue
                cid = row["strip"][k]
                if landed and k in option_at:
                    im = tile(cid, "gold" if option_at[k] == 0 else row["color"])
                elif landed:
                    im = dimmed(cid)
                else:
                    im = plain.get(cid) or tile(cid, None)
                # Clip to the window.
                left, right = max(0, win_x0 - x), min(CARD, win_x1 - x)
                if right <= left:
                    continue
                frame.paste(im.crop((left, 0, right, CARD)), (x + left, cy))
                if landed and k in option_at and left == 0:
                    d.text((x + 5, cy + 3), str(option_at[k] + 1), fill=GOLD, font=num_font)
            # The marker.
            d.polygon([(marker - 6, cy - 6), (marker + 6, cy - 6), (marker, cy + 2)], fill=GOLD)
            d.polygon([(marker - 6, cy + CARD + 6), (marker + 6, cy + CARD + 6), (marker, cy + CARD - 2)], fill=GOLD)
            if not landed:
                d.line([(marker, cy), (marker, cy + CARD)], fill=GOLD, width=1)
            # Once it stops: the options' names under the reel.
            if landed:
                names = [cards.get(c, {}).get("name", c) for c in row["options"]]
                text = "  ".join(f"{i + 1} {n}" for i, n in enumerate(names))
                d.text((win_x0 + 2, cy + CARD + 8), text, fill=MUTED, font=small_font)
        frames.append(frame)

    # One palette for every frame (from the final frame, which has every lit card and colour): much
    # faster than a palette per frame, and rows that stopped stay byte-identical, so later frames
    # only store the rows still moving.
    palette = frames[-1].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    paletted = [fr.quantize(palette=palette, dither=Image.Dither.NONE) for fr in frames]
    out = io.BytesIO()
    durations_ms = [round(1000 / FPS)] * (len(paletted) - 1) + [HOLD_MS]
    paletted[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=paletted[1:],
        duration=durations_ms,
        optimize=False,
        disposal=1,
    )
    return out.getvalue()


async def render(spec: dict, http: httpx.AsyncClient | None = None) -> bytes:
    """The GIF's bytes. Fetches the portraits it hasn't seen yet, then draws in a worker thread."""
    urls = {c["image"] for c in spec["cards"].values() if c.get("image")}
    icons = await _fetch_icons(urls, http)
    return await asyncio.to_thread(draw, spec, icons)
