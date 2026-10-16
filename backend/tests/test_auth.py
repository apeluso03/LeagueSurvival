"""Accounts, invites and who may do what (SPEC 12)."""

from datetime import timedelta

import pytest
from sqlmodel import select

from app.models import Invite, Run, User, utcnow
from app.services import auth
from tests.conftest import TEST_PASSWORD, make_user

PW = "hunter2hunter2"


def make_run(client, name="Run 1") -> dict:
    r = client.post("/api/runs", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def give_gold(client, run_id, player_id, amount=5000):
    r = client.post(f"/api/runs/{run_id}/players/{player_id}/gold/adjust", json={"amount": amount, "note": "test"})
    assert r.status_code == 200, r.text


# --- passwords and sign-in ---


def test_password_hashes_verify_and_are_salted():
    a, b = auth.hash_password("pa55word!"), auth.hash_password("pa55word!")
    assert a != b and a.startswith("scrypt$")
    assert auth.verify_password("pa55word!", a)
    assert not auth.verify_password("pa55word?", a)
    assert not auth.verify_password("x", "garbage")


def test_first_account_sets_up_the_site_and_adopts_old_runs(anon_client, session):
    session.add(Run(name="Before logins"))
    session.commit()
    me = anon_client.get("/api/auth/me").json()
    assert me["user"] is None and me["setup_needed"] is True
    assert [p["display_name"] for p in me["players"]][:2] == ["Alex", "Bea"]

    r = anon_client.post("/api/auth/setup", json={"username": "Alex", "password": PW, "player_id": 1})
    assert r.status_code == 200, r.text
    assert r.json()["user"] == {"id": 1, "username": "alex", "player_id": 1, "is_admin": True}
    assert anon_client.get("/api/auth/me").json()["user"]["username"] == "alex"  # cookie set
    assert anon_client.get("/api/runs").json()[0]["owner_user_id"] == 1

    # Setup only works once, and the roster isn't shown to strangers after that.
    anon_client.cookies.clear()
    assert anon_client.post("/api/auth/setup", json={"username": "evil", "password": PW}).status_code == 409
    assert anon_client.get("/api/auth/me").json() == {"user": None, "setup_needed": False, "players": []}


def test_everything_but_sign_in_needs_an_account(anon_client, owner):
    for method, path in [
        ("get", "/api/runs"),
        ("get", "/api/players"),
        ("get", "/api/settings"),
        ("post", "/api/runs/1/spins"),
        ("get", "/api/accounts"),
    ]:
        assert getattr(anon_client, method)(path).status_code == 401, path
    assert anon_client.get("/api/health").status_code == 200


def test_login_logout_and_wrong_password(anon_client, owner):
    assert anon_client.post("/api/auth/login", json={"username": "owner", "password": "nope-nope"}).status_code == 401
    assert anon_client.post("/api/auth/login", json={"username": "nobody", "password": PW}).status_code == 401
    r = anon_client.post("/api/auth/login", json={"username": "  OWNER ", "password": TEST_PASSWORD})
    assert r.status_code == 200 and r.json()["user"]["is_admin"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert anon_client.get("/api/runs").status_code == 200

    assert anon_client.post("/api/auth/logout").status_code == 204
    assert anon_client.get("/api/runs").status_code == 401


def test_logout_ends_the_session_on_the_server(anon_client, owner, session):
    token = anon_client.post("/api/auth/login", json={"username": "owner", "password": TEST_PASSWORD}).cookies[
        auth.SESSION_COOKIE
    ]
    anon_client.post("/api/auth/logout")
    anon_client.cookies.set(auth.SESSION_COOKIE, token)  # a copied cookie no longer works
    assert anon_client.get("/api/runs").status_code == 401


def test_expired_sessions_are_rejected(anon_client, owner, session):
    token = auth.start_session(session, owner)
    session.commit()
    row = session.exec(select(auth.AuthSession)).one()
    row.expires_at = utcnow() - timedelta(minutes=1)
    session.add(row)
    session.commit()
    anon_client.cookies.set(auth.SESSION_COOKIE, token)
    assert anon_client.get("/api/runs").status_code == 401


def test_repeated_wrong_passwords_are_throttled(anon_client, owner):
    for _ in range(5):
        anon_client.post("/api/auth/login", json={"username": "owner", "password": "wrong-wrong"})
    r = anon_client.post("/api/auth/login", json={"username": "owner", "password": TEST_PASSWORD})
    assert r.status_code == 429 and "Try again" in r.json()["detail"]


def test_throttle_window_expires():
    now = [0.0]
    t = auth.LoginThrottle(limit=2, window=60, clock=lambda: now[0])
    t.miss("k")
    t.miss("k")
    assert t.wait_seconds("k") == 60
    now[0] = 61
    assert t.wait_seconds("k") == 0


def test_change_password_signs_out_other_browsers(owner, sign_in, anon_client):
    here, elsewhere = sign_in(owner), sign_in(owner)
    bad = here.post("/api/auth/password", json={"current_password": "wrong-wrong", "new_password": PW})
    assert bad.status_code == 403
    assert here.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": "short"}).status_code == 400
    r = here.post("/api/auth/password", json={"current_password": TEST_PASSWORD, "new_password": PW})
    assert r.status_code == 200
    assert here.get("/api/runs").status_code == 200  # this browser got a fresh session
    assert elsewhere.get("/api/runs").status_code == 401
    assert anon_client.post("/api/auth/login", json={"username": "owner", "password": PW}).status_code == 200


# --- invites ---


def test_invite_link_signs_up_as_that_player(client, anon_client, session):
    r = client.post("/api/accounts/invites", json={"player_id": 2})
    assert r.status_code == 201
    token = r.json()["token"]
    assert session.exec(select(Invite)).one().token_hash != token  # only the hash is stored

    info = anon_client.get(f"/api/auth/invites/{token}").json()
    assert info["display_name"] == "Bea"
    taken = anon_client.post("/api/auth/register", json={"token": token, "username": "owner", "password": PW})
    assert taken.status_code == 409
    r = anon_client.post("/api/auth/register", json={"token": token, "username": "bea", "password": PW})
    assert r.status_code == 200
    assert r.json()["user"] == {"id": 2, "username": "bea", "player_id": 2, "is_admin": False}

    # One-time: the link is spent, and Bea now shows as having an account.
    anon_client.cookies.clear()
    assert anon_client.get(f"/api/auth/invites/{token}").status_code == 410
    assert anon_client.post("/api/auth/register", json={"token": token, "username": "bea2", "password": PW}).status_code == 410
    players = {p["id"]: p for p in client.get("/api/players").json()}
    assert players[2]["username"] == "bea" and players[3]["username"] is None
    assert client.post("/api/accounts/invites", json={"player_id": 2}).status_code == 409


def test_new_invite_replaces_the_old_and_owner_can_revoke(client, anon_client):
    old = client.post("/api/accounts/invites", json={"player_id": 3}).json()
    new = client.post("/api/accounts/invites", json={"player_id": 3}).json()
    assert anon_client.get(f"/api/auth/invites/{old['token']}").status_code == 404
    assert [i["id"] for i in client.get("/api/accounts").json()["invites"]] == [new["id"]]
    assert client.delete(f"/api/accounts/invites/{new['id']}").status_code == 204
    assert anon_client.get(f"/api/auth/invites/{new['token']}").status_code == 404
    assert anon_client.get("/api/auth/invites/made-up-token").status_code == 404


def test_expired_invite(client, anon_client, session):
    token = client.post("/api/accounts/invites", json={"player_id": 3}).json()["token"]
    invite = session.exec(select(Invite)).one()
    invite.expires_at = utcnow() - timedelta(seconds=1)
    session.add(invite)
    session.commit()
    assert anon_client.post("/api/auth/register", json={"token": token, "username": "cal", "password": PW}).status_code == 410


@pytest.mark.parametrize("username", ["ab", "has space", "x" * 25, "émile"])
def test_bad_usernames(client, anon_client, username):
    token = client.post("/api/accounts/invites", json={"player_id": 3}).json()["token"]
    r = anon_client.post("/api/auth/register", json={"token": token, "username": username, "password": PW})
    assert r.status_code == 400


def test_removing_an_account_keeps_the_player(client, session, sign_in):
    bea = make_user(session, "bea", player_id=2)
    bea_client = sign_in(bea)
    assert client.delete("/api/players/2").status_code == 409  # someone plays as Bea
    assert client.delete(f"/api/accounts/{bea.id}").status_code == 204
    assert bea_client.get("/api/runs").status_code == 401
    assert client.get("/api/players").json()[1]["display_name"] == "Bea"
    assert client.post("/api/accounts/invites", json={"player_id": 2}).status_code == 201
    assert client.delete("/api/accounts/1").status_code == 400  # not yourself


def test_only_the_site_owner_manages_accounts(session, sign_in):
    bea = sign_in(make_user(session, "bea", player_id=2))
    assert bea.get("/api/accounts").status_code == 403
    assert bea.post("/api/accounts/invites", json={"player_id": 3}).status_code == 403


# --- permissions ---


@pytest.fixture
def table(client, session, sign_in):
    """A run owned by the site owner, with Bea (player 2) and Cal (player 3) signed in."""
    run = make_run(client)
    for pid in (2, 3):
        give_gold(client, run["id"], pid)
    bea = sign_in(make_user(session, "bea", player_id=2))
    cal = sign_in(make_user(session, "cal", player_id=3))
    return run, bea, cal


def test_players_cannot_run_the_game(table, client):
    run, bea, _ = table
    rid = run["id"]
    assert bea.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2, 3]}).status_code == 403
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [1, 2, 3]}).json()["game"]
    gid = game["id"]
    picks = [{"player_id": 2, "option_index": 0}]
    assert bea.patch(f"/api/games/{gid}/assignments", json={"picks": picks}).status_code == 403
    assert bea.post(f"/api/games/{gid}/result", json={"result": "win"}).status_code == 403
    assert bea.post(f"/api/games/{gid}/link-match", json={"riot_match_id": "NA1_1"}).status_code == 403
    assert client.post(f"/api/games/{gid}/result", json={"result": "win"}).status_code == 200
    assert bea.post(f"/api/games/{gid}/undo").status_code == 403

    for method, path, body in [
        ("patch", "/api/settings", {"challenge_mode": False}),
        ("post", "/api/runs", {"name": "Mine"}),
        ("post", f"/api/runs/{rid}/end", None),
        ("delete", f"/api/runs/{rid}", None),
        ("patch", f"/api/runs/{rid}/shop-config", {"prices": {"shield": 1}}),
        ("post", f"/api/runs/{rid}/pool/Champ000/eliminate", None),
        ("post", f"/api/runs/{rid}/pool/Champ000/revive", {}),
        ("post", f"/api/runs/{rid}/players/2/gold/adjust", {"amount": 999, "note": "pls"}),
        ("post", "/api/players", {"display_name": "Zed"}),
        ("delete", "/api/players/4", None),
        ("post", "/api/sync", None),
        ("post", "/api/champions/refresh", None),
    ]:
        kwargs = {"json": body} if body is not None else {}
        r = getattr(bea, method)(path, **kwargs)
        assert r.status_code == 403, (method, path, r.status_code)
    # Reading is fine.
    for path in (f"/api/runs/{rid}", f"/api/runs/{rid}/pool", f"/api/games?run_id={rid}", "/api/settings", "/api/stats/players"):
        assert bea.get(path).status_code == 200, path


def test_players_see_and_spend_only_their_own_gold(table, client):
    run, bea, _ = table
    rid = run["id"]
    assert bea.get(f"/api/runs/{rid}/players/2/gold").json()["balance"] == 5000
    assert bea.get(f"/api/runs/{rid}/players/3/gold").status_code == 403
    assert bea.get(f"/api/runs/{rid}/players/3/inventory").status_code == 403
    assert [row["player_id"] for row in bea.get(f"/api/runs/{rid}/economy").json()] == [2]
    assert len(client.get(f"/api/runs/{rid}/economy").json()) == 6  # the owner sees everyone

    assert bea.post(f"/api/runs/{rid}/players/2/purchase", json={"type": "shield"}).status_code == 200
    assert bea.post(f"/api/runs/{rid}/players/3/purchase", json={"type": "shield"}).status_code == 403

    stats = {s["player_id"]: s for s in bea.get(f"/api/stats/players?run_id={rid}").json()}
    assert stats[2]["gold_balance"] is not None and stats[3]["gold_balance"] is None
    assert stats[3]["gold_earned"] == 5000  # earned is a public stat
    owner_stats = {s["player_id"]: s for s in client.get(f"/api/stats/players?run_id={rid}").json()}
    assert owner_stats[3]["gold_balance"] == 5000


def test_players_use_only_their_own_items(table, client):
    run, bea, cal = table
    rid = run["id"]
    cal_shield = cal.post(f"/api/runs/{rid}/players/3/purchase", json={"type": "shield"}).json()["item"]
    assert bea.post(f"/api/items/{cal_shield['id']}/use", json={"champion_id": "Champ001"}).status_code == 403
    assert cal.post(f"/api/items/{cal_shield['id']}/use", json={"champion_id": "Champ001"}).status_code == 200

    # The run's owner can buy and use items for anyone (single-user play still works).
    bought = client.post(f"/api/runs/{rid}/players/2/purchase", json={"type": "shield"}).json()["item"]
    assert client.post(f"/api/items/{bought['id']}/use", json={"champion_id": "Champ002"}).status_code == 200


def test_players_use_only_their_own_revive_tokens(table, client, session):
    run, bea, cal = table
    rid = run["id"]
    from app.models import ReviveToken

    # Lose a game to have something to revive, then hand out tokens.
    game = client.post(f"/api/runs/{rid}/spins", json={"player_ids": [2, 3]}).json()["game"]
    client.patch(f"/api/games/{game['id']}/assignments", json={"picks": [{"player_id": 2, "option_index": 0}, {"player_id": 3, "option_index": 0}]})
    lost = client.post(f"/api/games/{game['id']}/result", json={"result": "loss"}).json()
    dead = lost["eliminated"][0]
    session.add_all([ReviveToken(run_id=rid, player_id=p, earned_in_game_id=game["id"]) for p in (2, 3)])
    session.commit()
    tokens = {t["player_id"]: t["id"] for t in bea.get(f"/api/tokens?run_id={rid}").json()}

    assert bea.post(f"/api/tokens/{tokens[3]}/use", json={"champion_id": dead}).status_code == 403
    assert bea.post(f"/api/runs/{rid}/pool/{dead}/revive", json={"token_id": tokens[3]}).status_code == 403
    assert bea.post(f"/api/tokens/{tokens[2]}/use", json={"champion_id": dead}).status_code == 200


def test_players_edit_only_their_own_look(table):
    _, bea, _ = table
    assert bea.patch("/api/players/2", json={"color": "#112233"}).status_code == 200
    assert bea.patch("/api/players/2", json={"display_name": "Queen"}).status_code == 403
    assert bea.patch("/api/players/2", json={"riot_game_name": "x", "riot_tag_line": "y"}).status_code == 403
    assert bea.patch("/api/players/3", json={"color": "#112233"}).status_code == 403


def test_profiles_hide_other_players_items_and_gold(table):
    run, bea, _ = table
    rid = run["id"]
    mine = bea.get(f"/api/players/2/profile?run_id={rid}").json()
    theirs = bea.get(f"/api/players/3/profile?run_id={rid}").json()
    assert mine["items"] is not None and mine["gold_timeline"]
    assert theirs["items"] is None and theirs["gold_timeline"] is None
    assert theirs["stats"]["gold_balance"] is None


def test_a_run_owner_who_is_not_the_site_owner(client, session, sign_in):
    """Run ownership is per run: Dee owns her run but not the site owner's."""
    alex_run = make_run(client, "Alex's run")
    dee = make_user(session, "dee", player_id=4)
    dee_run = session.get(Run, make_run(client, "Dee's run")["id"])
    dee_run.owner_user_id = dee.id
    session.add(dee_run)
    session.commit()
    dc = sign_in(dee)
    assert dc.post(f"/api/runs/{dee_run.id}/spins", json={"player_ids": [1, 2]}).status_code == 200
    assert dc.post(f"/api/runs/{alex_run['id']}/spins", json={"player_ids": [1, 2]}).status_code == 403
    give_gold(client, dee_run.id, 2)
    assert dc.get(f"/api/runs/{dee_run.id}/players/2/gold").status_code == 200  # her run: everyone's shop
    assert dc.get(f"/api/runs/{alex_run['id']}/players/2/gold").status_code == 403
    assert dc.patch("/api/settings", json={"poll_interval_seconds": 60}).status_code == 403  # site settings


def test_deleting_a_user_releases_their_runs(client, session):
    bea = make_user(session, "bea", player_id=2)
    run = session.get(Run, make_run(client)["id"])
    run.owner_user_id = bea.id
    session.add(run)
    session.commit()
    bea_id, run_id = bea.id, run.id
    assert client.delete(f"/api/accounts/{bea_id}").status_code == 204
    session.expire_all()
    assert session.get(Run, run_id).owner_user_id is None
    assert session.get(User, bea_id) is None
