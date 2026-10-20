"""Groups: starting one, joining one, switching, members, site invites, and that groups never see
each other's data (SPEC 12.4)."""

import pytest

from app.models import Group, GroupMember, User
from app.services import auth
from tests.conftest import make_user

PW = "hunter2hunter2"


def site_code(client, note="for zed") -> str:
    r = client.post("/api/site/invites", json={"note": note})
    assert r.status_code == 201, r.text
    return r.json()["code"]


@pytest.fixture
def zed(client, anon_client):
    """A second group: Zed signs up with a site invite code and adds two players and a run."""
    code = site_code(client)
    r = anon_client.post("/api/auth/signup", json={"username": "zed", "password": PW, "group_name": "Zed's crew", "code": code})
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["group"]["name"] == "Zed's crew" and me["group"]["role"] == "owner" and not me["user"]["is_admin"]
    for name in ("Zara", "Zack"):
        assert anon_client.post("/api/players", json={"display_name": name}).status_code == 201
    run = anon_client.post("/api/runs", json={"name": "Zed run"})
    assert run.status_code == 201, run.text
    return anon_client


def test_groups_never_see_each_other(client, zed):
    mine = client.post("/api/runs", json={"name": "Owner run"}).json()
    spin = client.post(f"/api/runs/{mine['id']}/spins", json={"player_ids": [1, 2]}).json()
    game_id = spin["game"]["id"]

    # Lists only show your own group.
    assert [p["display_name"] for p in zed.get("/api/players").json()] == ["Zack", "Zara"]
    assert [r["name"] for r in zed.get("/api/runs").json()] == ["Zed run"]
    assert zed.get("/api/games").json() == []
    assert [s["player_id"] for s in zed.get("/api/stats/players").json()] == [8, 7]  # Zack, Zara
    assert len(client.get("/api/players").json()) == 6

    # Anything in another group is "not found", read or write.
    for method, path, body in [
        ("get", f"/api/runs/{mine['id']}", None),
        ("get", f"/api/runs/{mine['id']}/pool", None),
        ("get", f"/api/runs/{mine['id']}/recap", None),
        ("get", f"/api/games/{game_id}", None),
        ("get", f"/api/games/{game_id}/live", None),
        ("get", "/api/players/1/profile", None),
        ("get", f"/api/stats/players?run_id={mine['id']}", None),
        ("get", f"/api/champions/Champ001/stats?run_id={mine['id']}", None),
        ("get", f"/api/runs/{mine['id']}/players/1/gold", None),
        ("post", f"/api/runs/{mine['id']}/spins", {"player_ids": [7, 8]}),
        ("post", f"/api/games/{game_id}/result", {"result": "loss"}),
        ("patch", "/api/players/1", {"color": "#112233"}),
        ("post", "/api/accounts/invites", {"player_id": 1}),
    ]:
        kwargs = {"json": body} if body is not None else {}
        r = getattr(zed, method)(path, **kwargs)
        assert r.status_code == 404, (method, path, r.status_code, r.text)

    # And the other way round: the site admin has no powers inside Zed's group.
    zed_run = zed.get("/api/runs").json()[0]["id"]
    assert client.get(f"/api/runs/{zed_run}").status_code == 404
    assert client.post(f"/api/runs/{zed_run}/spins", json={"player_ids": [1, 2]}).status_code == 404


def test_spins_only_take_your_own_players(client, zed):
    zed_run = zed.get("/api/runs").json()[0]["id"]
    assert zed.post(f"/api/runs/{zed_run}/spins", json={"player_ids": [7, 1]}).status_code == 404
    assert zed.post(f"/api/runs/{zed_run}/spins", json={"player_ids": [7, 8]}).status_code == 200


def test_settings_trophies_and_shame_are_per_group(client, zed):
    assert zed.patch("/api/settings", json={"challenge_mode": False}).status_code == 200
    assert client.get("/api/settings").json()["challenge_mode"] is True
    run = client.post("/api/runs", json={"name": "R"}).json()
    game = client.post(f"/api/runs/{run['id']}/spins", json={"player_ids": [1, 2]}).json()["game"]
    client.patch(f"/api/games/{game['id']}/assignments", json={"picks": [{"player_id": 1, "option_index": 0}, {"player_id": 2, "option_index": 0}]})
    client.post(f"/api/games/{game['id']}/result", json={"result": "loss"})
    assert set(client.get("/api/achievements").json()["players"]) >= {"1"}
    assert zed.get("/api/achievements").json()["players"] == {}
    assert zed.get("/api/shame").json()["worst_games"] == []
    assert zed.get("/api/wrapped").json()["games"] == 0
    # The build crawler is the site admin's, not a group owner's.
    assert zed.patch("/api/settings", json={"meta_crawl": False}).status_code == 403
    assert client.patch("/api/settings", json={"meta_crawl": False}).status_code == 200


def test_starting_a_group_needs_a_code_until_signup_opens(client, anon_client):
    body = {"username": "newbie", "password": PW, "group_name": "Newbies"}
    assert anon_client.post("/api/auth/signup", json=body).status_code == 403
    assert anon_client.post("/api/auth/signup", json={**body, "code": "made-up"}).status_code == 404
    code = site_code(client)
    assert anon_client.post("/api/auth/signup", json={**body, "code": code}).status_code == 200
    anon_client.cookies.clear()
    again = anon_client.post("/api/auth/signup", json={**body, "username": "newbie2", "code": code})
    assert again.status_code == 410  # one-time

    assert client.patch("/api/site", json={"open_signup": True}).json()["open_signup"] is True
    assert anon_client.get("/api/auth/me").json()["open_signup"] is True
    assert anon_client.post("/api/auth/signup", json={**body, "username": "newbie3"}).status_code == 200


def test_group_names_are_checked(client, anon_client):
    code = site_code(client)
    r = anon_client.post("/api/auth/signup", json={"username": "x_user", "password": PW, "group_name": " ", "code": code})
    assert r.status_code == 400


def test_only_the_site_admin_runs_the_site(zed):
    assert zed.get("/api/site").status_code == 403
    assert zed.post("/api/site/invites", json={}).status_code == 403
    assert zed.patch("/api/site", json={"open_signup": True}).status_code == 403
    assert zed.post("/api/privacy/purge", json={"confirm": "DELETE"}).status_code == 403


def test_join_a_second_group_and_switch(client, zed, session):
    # Zed invites the site admin into Zed's group as Zara.
    token = zed.post("/api/accounts/invites", json={"player_id": 7}).json()["token"]
    me = client.post(f"/api/auth/invites/{token}/accept").json()
    assert me["group"] == {"id": 2, "name": "Zed's crew", "role": "member", "player_id": 7}
    assert [g["id"] for g in me["groups"]] == [1, 2]
    # Now viewing Zed's group, as a member: can't run it.
    assert [p["display_name"] for p in client.get("/api/players").json()] == ["Zack", "Zara"]
    zed_run = client.get("/api/runs").json()[0]["id"]
    assert client.post(f"/api/runs/{zed_run}/spins", json={"player_ids": [7, 8]}).status_code == 403
    # Switch back.
    assert client.post("/api/groups/1/switch").json()["group"]["role"] == "owner"
    assert len(client.get("/api/players").json()) == 6
    assert client.post("/api/groups/99/switch").status_code == 404
    # Already in it: can't join twice.
    token2 = zed.post("/api/accounts/invites", json={"player_id": 8}).json()["token"]
    assert client.post(f"/api/auth/invites/{token2}/accept").status_code == 409


def test_start_another_group_while_signed_in(client, zed):
    # The site admin can always start a group; others need a code (sign-up is closed).
    assert zed.post("/api/groups", json={"name": "Second crew"}).status_code == 403
    me = client.post("/api/groups", json={"name": "Admin's second"}).json()
    assert me["group"]["name"] == "Admin's second" and me["group"]["role"] == "owner"
    assert client.get("/api/players").json() == []
    assert client.get("/api/settings").json()["challenge_mode"] is True  # its own settings
    assert client.patch("/api/groups/current", json={"name": "Renamed"}).json()["group"]["name"] == "Renamed"


def test_removing_members(client, session, sign_in):
    bea = make_user(session, "bea", player_id=2)
    bea_client = sign_in(bea)
    owner_id = client.get("/api/auth/me").json()["user"]["id"]
    assert client.delete(f"/api/accounts/{owner_id}").status_code == 400  # not yourself
    bea_id = bea.id
    assert client.delete(f"/api/accounts/{bea_id}").status_code == 204
    session.expire_all()
    assert session.get(User, bea_id) is None  # in no group any more: account gone, name free
    assert bea_client.get("/api/runs").status_code == 401
    assert client.post("/api/accounts/invites", json={"player_id": 2}).status_code == 201


def test_member_in_two_groups_keeps_their_account(client, zed, session):
    token = zed.post("/api/accounts/invites", json={"player_id": 7}).json()["token"]
    bea = make_user(session, "bea", player_id=2)
    assert auth.accept_invite_signed_in(session, token, bea)
    session.commit()
    assert client.delete(f"/api/accounts/{bea.id}").status_code == 204
    session.expire_all()
    assert session.get(User, bea.id) is not None
    assert session.get(GroupMember, (2, bea.id)) is not None


def test_owner_cannot_be_removed(session):
    owner = make_user(session, "own2", role="owner")
    with pytest.raises(Exception):
        auth.remove_member(session, session.get(Group, 1), owner)


def test_members_without_a_group_are_asked_to_start_or_join(session, sign_in):
    loner = sign_in(make_user(session, "loner", role=None))
    r = loner.get("/api/runs")
    assert r.status_code == 409 and "group" in r.json()["detail"]
    assert loner.get("/api/auth/me").json()["group"] is None
