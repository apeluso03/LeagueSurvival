import asyncio

import httpx
import pytest

from app.services.riot_client import RateLimiter, RiotClient, RiotError, RiotNotConfigured


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def run(coro):
    return asyncio.run(coro)


def client_with(handler, clock=None):
    clock = clock or FakeClock()
    limiter = RateLimiter(limits=((100, 1.0),), clock=clock, sleep=clock.sleep)
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return RiotClient(api_key="RGAPI-test", http=http, limiter=limiter, sleep=clock.sleep), clock


def test_sends_key_and_builds_urls():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req)
        return httpx.Response(200, json={"puuid": "abc", "gameName": "Some Name", "tagLine": "NA1"})

    client, _ = client_with(handler)
    run(client.account_by_riot_id("americas", "Some Name", "NA1"))
    req = seen[0]
    assert req.headers["X-Riot-Token"] == "RGAPI-test"
    assert req.url.host == "americas.api.riotgames.com"
    assert req.url.raw_path == b"/riot/account/v1/accounts/by-riot-id/Some%20Name/NA1"


def test_match_ids_params():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=["NA1_1"])

    client, _ = client_with(handler)
    assert run(client.match_ids("americas", "puuid-1", start_time=123, count=5)) == ["NA1_1"]
    assert seen[0].url.params["startTime"] == "123" and seen[0].url.params["count"] == "5"


def test_retries_after_429_using_retry_after():
    responses = iter([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json={"ok": 1})])
    client, clock = client_with(lambda req: next(responses))
    assert run(client.match("americas", "NA1_1")) == {"ok": 1}
    assert 7.0 in clock.slept


def test_gives_up_after_repeated_429():
    client, _ = client_with(lambda req: httpx.Response(429, headers={"Retry-After": "1"}))
    with pytest.raises(RiotError) as e:
        run(client.match("americas", "NA1_1"))
    assert e.value.status == 429


def test_retries_server_errors():
    responses = iter([httpx.Response(503), httpx.Response(200, json=[])])
    client, _ = client_with(lambda req: next(responses))
    assert run(client.match_ids("americas", "p")) == []


@pytest.mark.parametrize("status", [401, 403, 404])
def test_client_errors_raise(status):
    client, _ = client_with(lambda req: httpx.Response(status, json={"status": {"message": "nope"}}))
    with pytest.raises(RiotError) as e:
        run(client.match("americas", "x"))
    assert e.value.status == status


def test_no_key_raises_not_configured():
    client = RiotClient(api_key="", http=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: None)))
    with pytest.raises(RiotNotConfigured):
        run(client.match("americas", "x"))


def test_rate_limiter_waits_when_window_is_full():
    clock = FakeClock()
    limiter = RateLimiter(limits=((2, 1.0), (3, 10.0)), clock=clock, sleep=clock.sleep)

    async def go():
        for _ in range(4):
            await limiter.acquire()

    run(go())
    # 2 calls fill the 1s window -> wait 1s; the 3rd fills the 10s window -> the 4th waits until t=10
    assert clock.now == pytest.approx(10.0)
