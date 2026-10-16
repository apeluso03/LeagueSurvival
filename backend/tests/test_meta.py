import asyncio
import random

from sqlmodel import select

from app.models import Champion, MetaChampRole, MetaCrawlState, MetaItem, MetaMatch, MetaRunePage
from app.services import meta


def participant(champ_key: int, role: str, win: bool, items=(3078, 3047, 6333, 2003), keystone=8010):
    return {
        "championId": champ_key,
        "teamPosition": role,
        "win": win,
        **{f"item{i}": item for i, item in enumerate(items)},
        "item6": 3340,
        "perks": {
            "statPerks": {"offense": 5005, "flex": 5008, "defense": 5011},
            "styles": [
                {"description": "primaryStyle", "style": 8000, "selections": [{"perk": keystone}, {"perk": 9111}, {"perk": 9104}, {"perk": 8299}]},
                {"description": "subStyle", "style": 8400, "selections": [{"perk": 8444}, {"perk": 8451}]},
            ],
        },
    }


def ranked_match(match_id: str, participants, patch="16.20.1.1", queue=420, duration=1800):
    return {
        "metadata": {"matchId": match_id},
        "info": {"queueId": queue, "gameVersion": patch, "gameDuration": duration, "participants": participants},
    }


def test_patch_and_rune_page_key():
    assert meta.patch_of("16.20.712.1234") == "16.20"
    key = meta.rune_page_key(participant(1, "TOP", True)["perks"])
    assert key == "8000:8010,9111,9104,8299|8400:8444,8451|5005,5008,5011"


def test_count_match_aggregates_and_skips_duplicates(session):
    m = ranked_match("NA1_1", [participant(1000, "TOP", True), participant(1001, "UTILITY", False)])
    assert meta.count_match(session, m)
    assert not meta.count_match(session, m)  # already counted
    assert not meta.count_match(session, ranked_match("NA1_2", [participant(1000, "TOP", True)], queue=450))
    assert not meta.count_match(session, ranked_match("NA1_3", [participant(1000, "TOP", True)], duration=600))
    row = session.get(MetaChampRole, (1000, "TOP", "16.20"))
    assert (row.games, row.wins) == (1, 1)
    items = {i.item_id for i in session.exec(select(MetaItem).where(MetaItem.champion_key == 1000)).all()}
    assert items == {3078, 3047, 6333, 2003}  # trinket left out
    assert session.exec(select(MetaRunePage)).all()


def test_role_assignment_from_positions(session):
    # Four champions whose positions point at four different roles; a fifth flexible one.
    positions = {"Champ001": ["TOP"], "Champ002": ["SUPPORT"], "Champ003": ["MIDDLE"], "Champ004": ["BOTTOM"]}
    for cid, pos in positions.items():
        c = session.get(Champion, cid)
        c.positions = pos
        session.add(c)
    session.flush()
    result = meta.suggest_comp(session, ["Champ001", "Champ002", "Champ003", "Champ004"])
    assert [(p.champion_id, p.role) for p in result["picks"]] == [
        ("Champ001", "TOP"),
        ("Champ002", "UTILITY"),
        ("Champ003", "MIDDLE"),
        ("Champ004", "BOTTOM"),
    ]
    assert all(p.role_source == "positions" for p in result["picks"])


def test_assignment_breaks_clashes():
    # Two mid laners: the one that can also top goes top.
    scores = [
        {"TOP": 0.02, "JUNGLE": 0.02, "MIDDLE": 1.0, "BOTTOM": 0.02, "UTILITY": 0.02},
        {"TOP": 0.6, "JUNGLE": 0.02, "MIDDLE": 1.0, "BOTTOM": 0.02, "UTILITY": 0.02},
    ]
    assert meta.best_assignment(scores) == ["MIDDLE", "TOP"]


def test_high_elo_data_wins_over_positions_and_gives_a_build(session):
    c = session.get(Champion, "Champ001")
    c.positions = ["TOP"]
    session.add(c)
    for i in range(25):  # mostly played jungle in high elo
        meta.count_match(session, ranked_match(f"NA1_{i}", [participant(1001, "JUNGLE", i % 3 != 0)]))
    static = {
        "items": {
            3078: {"name": "Trinity Force", "image": "x", "total": 3333, "boots": False, "final": True},
            3047: {"name": "Plated Steelcaps", "image": "y", "total": 1200, "boots": True, "final": True},
            6333: {"name": "Death's Dance", "image": "z", "total": 3300, "boots": False, "final": True},
            2003: {"name": "Health Potion", "image": "p", "total": 50, "boots": False, "final": True},
        },
        "perks": {8010: {"name": "Conqueror", "icon": "i"}},
    }
    pick = meta.suggest_comp(session, ["Champ001"], static)["picks"][0]
    assert pick.role == "JUNGLE" and pick.role_source == "high-elo" and pick.role_games == 25
    assert pick.runes["keystone"]["name"] == "Conqueror" and pick.runes["games"] == 25
    assert [i["name"] for i in pick.items] == ["Trinity Force", "Death's Dance"]  # potion isn't core
    assert pick.boots["name"] == "Plated Steelcaps"


class FakeLadderClient:
    def __init__(self):
        self.calls = []

    async def league(self, platform, tier):
        self.calls.append(("league", tier))
        return {"entries": [{"puuid": f"{tier}-{i}"} for i in range(3)]}

    async def summoner_by_id(self, platform, sid):  # pragma: no cover - entries carry PUUIDs here
        raise AssertionError

    async def match_ids(self, region, puuid, start_time=None, count=20, queue=None):
        self.calls.append(("ids", puuid, queue))
        return [f"{puuid}-m1", f"{puuid}-m2"]

    async def match(self, region, match_id):
        self.calls.append(("match", match_id))
        return ranked_match(match_id, [participant(1002, "MIDDLE", True)])


def test_crawl_step_refreshes_ladder_then_counts_matches(session):
    client = FakeLadderClient()
    random.seed(1)
    counted = asyncio.run(meta.crawl_step(session, client))
    state = session.get(MetaCrawlState, 1)
    assert counted == 2 and state.matches_counted == 2 and len(state.puuids) == 9 and state.next_index == 1
    assert ("ids", state.puuids[0], 420) in client.calls
    # Next step visits the next player without refreshing the ladder again.
    asyncio.run(meta.crawl_step(session, client))
    assert sum(1 for c in client.calls if c[0] == "league") == 3
    assert len(session.exec(select(MetaMatch)).all()) == 4


class LockCheckingClient(FakeLadderClient):
    """Fails the test if the crawler waits on Riot while holding a database transaction."""

    def __init__(self, session):
        super().__init__()
        self.session = session
        self.checked = 0

    def _check(self):
        assert not self.session.in_transaction(), "crawler held the database while waiting on Riot"
        self.checked += 1

    async def league(self, platform, tier):
        self._check()
        return await super().league(platform, tier)

    async def match_ids(self, region, puuid, start_time=None, count=20, queue=None):
        self._check()
        return await super().match_ids(region, puuid, start_time, count, queue)

    async def match(self, region, match_id):
        self._check()
        return await super().match(region, match_id)


def test_crawler_never_holds_the_database_while_waiting(session):
    client = LockCheckingClient(session)

    async def pause():
        assert not session.in_transaction()

    asyncio.run(meta.crawl_step(session, client, pause=pause))
    asyncio.run(meta.crawl_step(session, client, pause=pause))
    assert client.checked >= 3 + 2 * 3  # ladder (3 tiers) + two players (ids + 2 matches each)
    assert not session.in_transaction()


def test_prune_keeps_two_newest_patches(session):
    for patch in ("16.18.1", "16.19.1", "16.20.1"):
        meta.count_match(session, ranked_match(f"M{patch}", [participant(1000, "TOP", True)], patch=patch))
    meta.prune_old_patches(session)
    assert meta.recent_patches(session) == ["16.20", "16.19"]
    assert {r.patch for r in session.exec(select(MetaChampRole)).all()} == {"16.20", "16.19"}


def test_off_role_pick_borrows_the_usual_build(session):
    # Two top laners: one has to play somewhere else, and is flagged off-role with its top build.
    for cid in ("Champ001", "Champ002"):
        c = session.get(Champion, cid)
        c.positions = ["TOP"]
        session.add(c)
    for i in range(25):
        meta.count_match(session, ranked_match(f"A{i}", [participant(1001, "TOP", True, keystone=8010)]))
        meta.count_match(session, ranked_match(f"B{i}", [participant(1002, "TOP", True, keystone=8437)]))
    picks = meta.suggest_comp(session, ["Champ001", "Champ002"])["picks"]
    assert sorted(p.role for p in picks)[1] == "TOP"
    moved = next(p for p in picks if p.role != "TOP")
    assert moved.off_role and moved.build_role == "TOP" and moved.runes is not None
    assert not next(p for p in picks if p.role == "TOP").off_role


def test_parse_positions():
    data = {"Sion": {"positions": ["TOP"]}, "MonkeyKing": {"positions": ["JUNGLE", "TOP"]}, "Odd": {}}
    assert meta.parse_positions(data) == {"Sion": ["TOP"], "MonkeyKing": ["JUNGLE", "TOP"], "Odd": []}


def test_comp_endpoint_and_status(client, session):
    r = client.post("/api/comp", json={"champion_ids": ["Champ001", "Champ002"]})
    assert r.status_code == 200 and len(r.json()["picks"]) == 2
    assert client.post("/api/comp", json={"champion_ids": []}).status_code == 422
    s = client.get("/api/meta/status").json()
    assert s["enabled"] is True and s["key_set"] is False and s["matches"] == 0


# --- summoner spells, matchups and bans ---


def player(key, team, win, role="MIDDLE", spells=(4, 14)):
    p = participant(key, role, win)
    return {**p, "teamId": team, "summoner1Id": spells[0], "summoner2Id": spells[1]}


def game(match_id, blue, red, blue_wins=True):
    """blue/red: lists of (champion_key, role, spells)."""
    return ranked_match(
        match_id,
        [player(k, 100, blue_wins, r, sp) for k, r, sp in blue] + [player(k, 200, not blue_wins, r, sp) for k, r, sp in red],
    )


def test_spells_and_matchups_are_counted(session):
    from app.models import MetaMatchup, MetaSpells

    meta.count_match(session, game("NA1_10", [(1000, "TOP", (14, 4))], [(1001, "TOP", (4, 12)), (1002, "MIDDLE", (4, 14))]))
    assert session.get(MetaSpells, (1000, "TOP", "16.20", "4,14")).wins == 1  # stored lowest id first
    assert session.get(MetaMatchup, (1000, 1001, "16.20")).wins == 1
    assert session.get(MetaMatchup, (1001, 1000, "16.20")).wins == 0
    assert session.get(MetaMatchup, (1001, 1002, "16.20")) is None  # teammates aren't a matchup
    assert session.get(MetaMatch, "NA1_10").extras


def test_suggested_spells_put_flash_second(session):
    for i in range(3):
        meta.count_match(session, game(f"NA1_{20 + i}", [(1000, "TOP", (4, 12))], [(1001, "TOP", (4, 14))]))
    meta.count_match(session, game("NA1_29", [(1000, "TOP", (4, 14))], [(1001, "TOP", (4, 14))], blue_wins=False))
    champ = session.get(Champion, "Champ000")
    static = {"spells": {4: {"name": "Flash", "icon": "f.png"}, 12: {"name": "Teleport", "icon": "t.png"}}}
    out = meta.spells_for(session, champ, "TOP", ["16.20"], static)
    assert [s["name"] for s in out["spells"]] == ["Teleport", "Flash"]
    assert out["games"] == 3 and out["win_rate"] == 1.0 and out["pick_rate"] == 0.75


def test_bans_target_what_our_champs_lose_to(session):
    # Champ000 (key 1000) loses to 1005 every time, beats 1006, and has a coin-flip record vs 1007.
    n = 0
    for _ in range(12):
        n += 1
        meta.count_match(session, game(f"NA1_{100 + n}", [(1000, "MIDDLE", (4, 14))], [(1005, "MIDDLE", (4, 14))], blue_wins=False))
        n += 1
        meta.count_match(session, game(f"NA1_{100 + n}", [(1000, "MIDDLE", (4, 14))], [(1006, "MIDDLE", (4, 14))], blue_wins=True))
    for i in range(4):
        n += 1
        meta.count_match(session, game(f"NA1_{100 + n}", [(1000, "MIDDLE", (4, 14))], [(1007, "MIDDLE", (4, 14))], blue_wins=i % 2 == 0))
    # One loss to 1008: too little to beat a dozen losses to 1005.
    meta.count_match(session, game("NA1_999", [(1000, "MIDDLE", (4, 14))], [(1008, "MIDDLE", (4, 14))], blue_wins=False))

    bans = meta.suggest_bans(session, [session.get(Champion, "Champ000")], ["16.20"])
    ids = [b["champion_id"] for b in bans]
    assert ids[0] == "Champ005"
    assert "Champ006" not in ids  # we beat it
    assert bans[0]["games"] == 12 and bans[0]["win_rate"] == 0.0
    assert bans[0]["against"] == [{"champion_id": "Champ000", "games": 12, "win_rate": 0.0}]
    assert ids.index("Champ005") < ids.index("Champ008")


def test_bans_never_include_our_own_champions(session):
    for i in range(5):
        meta.count_match(session, game(f"NA1_{300 + i}", [(1000, "TOP", (4, 12))], [(1001, "TOP", (4, 12))], blue_wins=False))
    champs = [session.get(Champion, "Champ000"), session.get(Champion, "Champ001")]
    assert all(b["champion_id"] not in ("Champ000", "Champ001") for b in meta.suggest_bans(session, champs, ["16.20"]))


def test_suggest_comp_includes_spells_and_bans(session):
    for i in range(5):
        meta.count_match(session, game(f"NA1_{400 + i}", [(1000, "TOP", (4, 12))], [(1003, "TOP", (4, 14))], blue_wins=False))
        meta.count_match(session, game(f"NA1_{410 + i}", [(1000, "TOP", (4, 12))], [(1004, "TOP", (4, 14))], blue_wins=True))
    result = meta.suggest_comp(session, ["Champ000"])
    assert result["picks"][0].spells["spells"][0]["id"] == 12
    assert result["bans"][0]["champion_id"] == "Champ003"


class BackfillClient:
    def __init__(self, session, matches):
        self.session, self.matches, self.fetched = session, matches, []

    async def match(self, region, match_id):
        assert not self.session.in_transaction()
        self.fetched.append(match_id)
        if match_id not in self.matches:
            raise meta.RiotError(404, "gone")
        return self.matches[match_id]


def test_backfill_fills_in_old_matches(session):
    from app.models import MetaMatchup, MetaSpells

    old = game("NA1_500", [(1000, "TOP", (4, 12))], [(1001, "TOP", (4, 14))])
    session.add_all([MetaMatch(match_id="NA1_500", patch="16.20"), MetaMatch(match_id="NA1_501", patch="16.20")])
    session.commit()
    assert len(meta.needs_backfill(session)) == 2
    client = BackfillClient(session, {"NA1_500": old})
    assert asyncio.run(meta.backfill_step(session, client, "americas")) == 2
    assert session.get(MetaSpells, (1000, "TOP", "16.20", "4,12")).games == 1
    assert session.get(MetaMatchup, (1000, 1001, "16.20")).games == 1
    assert session.get(MetaChampRole, (1000, "TOP", "16.20")) is None  # roles/builds aren't counted twice
    assert meta.needs_backfill(session) == []  # the 404 one is marked done too
    assert asyncio.run(meta.backfill_step(session, client, "americas")) == 0
    assert meta.status(session)["backfill_remaining"] == 0


def test_bans_skip_excluded_champions(session):
    for i in range(6):
        meta.count_match(session, game(f"NA1_{600 + i}", [(1000, "TOP", (4, 12))], [(1003, "TOP", (4, 14))], blue_wins=False))
        meta.count_match(session, game(f"NA1_{610 + i}", [(1000, "TOP", (4, 12))], [(1004, "TOP", (4, 14))], blue_wins=False))
        meta.count_match(session, game(f"NA1_{620 + i}", [(1000, "TOP", (4, 12))], [(1005, "TOP", (4, 14))], blue_wins=True))
    ids = [b["champion_id"] for b in meta.suggest_comp(session, ["Champ000"], exclude=["Champ003"])["bans"]]
    assert "Champ004" in ids and "Champ003" not in ids  # Champ003 is someone's backup option
