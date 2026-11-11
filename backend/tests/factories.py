"""Builders for Riot Match-V5 / Account-V1 shaped data, and a fake Riot client."""

from dataclasses import dataclass

from app.services.riot_client import RiotError

GAME_START_MS = 1_760_000_000_000


@dataclass
class P:
    """One participant. Only the fields the app reads."""

    puuid: str
    champion_id: int
    team_id: int = 100
    win: bool = True
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    cs: int = 150
    jungle_cs: int = 0
    gold: int = 10000
    damage: int = 15000
    vision: int = 20
    early_surrender: bool = False
    position: str = "MIDDLE"
    doubles: int = 0
    triples: int = 0
    quadras: int = 0
    pentas: int = 0
    heals: int = 0
    shields: int = 0


def make_match(
    match_id: str,
    participants: list[P],
    queue_id: int = 400,
    duration: int = 1800,
    start_ms: int = GAME_START_MS,
) -> dict:
    """A Match-V5 response. Fills the remaining slots with random players so teams have 5 each."""
    people = list(participants)
    for team in (100, 200):
        team_win = next((p.win for p in people if p.team_id == team), team == 200)
        while sum(p.team_id == team for p in people) < 5:
            n = len(people)
            people.append(P(f"stranger-{n}", 900 + n, team, team_win, kills=1, deaths=1, assists=1))
    return {
        "metadata": {"matchId": match_id, "participants": [p.puuid for p in people]},
        "info": {
            "gameCreation": start_ms - 60_000,
            "gameStartTimestamp": start_ms,
            "gameEndTimestamp": start_ms + duration * 1000,
            "gameDuration": duration,
            "queueId": queue_id,
            "participants": [
                {
                    "puuid": p.puuid,
                    "championId": p.champion_id,
                    "teamId": p.team_id,
                    "win": p.win,
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "assists": p.assists,
                    "totalMinionsKilled": p.cs,
                    "neutralMinionsKilled": p.jungle_cs,
                    "goldEarned": p.gold,
                    "totalDamageDealtToChampions": p.damage,
                    "visionScore": p.vision,
                    "gameEndedInEarlySurrender": p.early_surrender,
                    "teamPosition": p.position,
                    "doubleKills": p.doubles,
                    "tripleKills": p.triples,
                    "quadraKills": p.quadras,
                    "pentaKills": p.pentas,
                    "totalHealsOnTeammates": p.heals,
                    "totalDamageShieldedOnTeammates": p.shields,
                }
                for p in people
            ],
            "teams": [{"teamId": t, "win": any(p.win for p in people if p.team_id == t)} for t in (100, 200)],
        },
    }


class FakeRiotClient:
    """Stands in for RiotClient. `accounts` maps (name, tag) -> puuid; `matches` maps id -> match JSON."""

    def __init__(self, accounts=None, matches=None, error: RiotError | None = None):
        self.accounts = accounts or {}
        self.matches = matches or {}
        self.error = error
        self.calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        pass

    def _maybe_fail(self):
        if self.error:
            raise self.error

    async def account_by_riot_id(self, region, game_name, tag_line):
        self.calls.append(("account", game_name, tag_line))
        self._maybe_fail()
        for (name, tag), puuid in self.accounts.items():
            if name.lower() == game_name.lower() and tag.lower() == tag_line.lower():
                return {"puuid": puuid, "gameName": name, "tagLine": tag}
        raise RiotError(404, "Not found on the Riot API")

    async def match_ids(self, region, puuid, start_time=None, count=20):
        self.calls.append(("ids", puuid))
        self._maybe_fail()
        ids = [mid for mid, m in self.matches.items() if puuid in m["metadata"]["participants"]]
        return sorted(ids, reverse=True)[:count]

    async def match(self, region, match_id):
        self.calls.append(("match", match_id))
        self._maybe_fail()
        return self.matches[match_id]

    async def platform_status(self, platform="na1"):
        self._maybe_fail()
        return {"id": platform.upper()}


class FakeDiscord:
    """Stands in for DiscordClient: records what would be posted or edited.

    `fail` maps a method name ("post", "edit", ...) to the DiscordError it raises.
    """

    def __init__(self, channels=None, token=None, me=None):
        self.app_id = "app-1"
        self.posts: list[tuple[str, dict]] = []  # (channel_id, message)
        self.edits: list[tuple[str, str, dict]] = []  # (channel_id, message_id, message)
        self.replies: list[tuple[str, dict]] = []
        self.reels: list[tuple[str, dict, str, bytes]] = []  # posts with a file: (channel, message, name, data)
        self.reply_files: list[tuple[str, str, bytes]] = []  # (token, name, data)
        self.followups: list[tuple[str, dict]] = []
        self.commands: list[dict] | None = None
        self.left: list[str] = []
        self.fail: dict = {}
        self._channels = channels if channels is not None else [{"id": "c1", "name": "general", "position": 0}]
        self.token = token or {"access_token": "at", "scope": "identify"}
        self.user = me or {"id": "d-owner"}
        self._next = 100

    def _maybe_fail(self, name):
        if name in self.fail:
            raise self.fail[name]

    async def post(self, channel_id, message, files=None):
        self._maybe_fail("post")
        if files:  # the spin reels: kept apart so `posts` stays the messages the bot edits
            self.reels += [(channel_id, message, name, data) for name, data in files]
            return f"r{len(self.reels)}"
        self._next += 1
        self.posts.append((channel_id, message))
        return f"m{self._next}"

    async def edit(self, channel_id, message_id, message):
        self._maybe_fail("edit")
        self.edits.append((channel_id, message_id, message))

    async def edit_reply(self, token, message, files=None):
        self.replies.append((token, message))
        self.reply_files += [(token, name, data) for name, data in files or []]

    async def followup(self, token, message):
        self.followups.append((token, message))

    async def channels(self, guild_id):
        self._maybe_fail("channels")
        return list(self._channels)

    async def leave(self, guild_id):
        self.left.append(guild_id)

    async def set_commands(self, commands):
        self.commands = commands

    async def exchange(self, code, redirect_uri):
        self._maybe_fail("exchange")
        return dict(self.token)

    async def me(self, access_token):
        return dict(self.user)
