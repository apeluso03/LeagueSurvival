"""Riot API client: Account-V1, Match-V5 and a status check, with rate limiting (SPEC 9).

The key stays on the backend. All calls go through `RiotClient._get`, which waits on a local
sliding-window limiter and retries on 429 (honouring Retry-After) and on 5xx errors.
"""

import asyncio
import time
from collections import deque
from urllib.parse import quote

import httpx

from app.config import get_settings

# Personal key defaults; see the Riot Developer Portal for your key's actual limits.
DEFAULT_LIMITS = ((20, 1.0), (100, 120.0))  # (requests, per seconds)
MAX_RETRIES = 3

REGIONS = ("americas", "europe", "asia", "sea")


class RiotError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class RiotNotConfigured(RiotError):
    def __init__(self):
        super().__init__(0, "No Riot API key set. Add RIOT_API_KEY to .env and restart the backend.")


class RateLimiter:
    """Sliding-window limiter over several (count, seconds) windows at once."""

    def __init__(self, limits=DEFAULT_LIMITS, clock=time.monotonic, sleep=asyncio.sleep):
        self.limits = limits
        self.clock = clock
        self.sleep = sleep
        self.calls: deque[float] = deque()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            while True:
                now = self.clock()
                longest = max(seconds for _, seconds in self.limits)
                while self.calls and now - self.calls[0] >= longest:
                    self.calls.popleft()
                wait = 0.0
                for count, seconds in self.limits:
                    recent = [t for t in self.calls if now - t < seconds]
                    if len(recent) >= count:
                        wait = max(wait, seconds - (now - recent[-count]))
                if wait <= 0:
                    self.calls.append(now)
                    return
                await self.sleep(wait)


class RiotClient:
    def __init__(
        self,
        api_key: str | None = None,
        http: httpx.AsyncClient | None = None,
        limiter: RateLimiter | None = None,
        sleep=asyncio.sleep,
    ):
        self.api_key = get_settings().riot_api_key if api_key is None else api_key
        self.http = http or httpx.AsyncClient(timeout=15)
        self.limiter = limiter or _shared_limiter
        self.sleep = sleep

    async def aclose(self) -> None:
        await self.http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def _get(self, host: str, path: str, params: dict | None = None):
        if not self.api_key:
            raise RiotNotConfigured()
        url = f"https://{host}.api.riotgames.com{path}"
        for attempt in range(MAX_RETRIES + 1):
            await self.limiter.acquire()
            try:
                res = await self.http.get(url, params=params, headers={"X-Riot-Token": self.api_key})
            except httpx.HTTPError as e:
                if attempt == MAX_RETRIES:
                    raise RiotError(503, f"Could not reach the Riot API: {e}") from e
                await self.sleep(1 + attempt)
                continue
            if res.status_code == 429 and attempt < MAX_RETRIES:
                await self.sleep(float(res.headers.get("Retry-After", 1)))
                continue
            if res.status_code >= 500 and attempt < MAX_RETRIES:
                await self.sleep(1 + attempt)
                continue
            if res.status_code >= 400:
                raise RiotError(res.status_code, _error_message(res))
            return res.json()
        raise RiotError(429, "Riot API rate limit: try again in a minute")  # pragma: no cover

    # --- endpoints ---

    async def account_by_riot_id(self, region: str, game_name: str, tag_line: str) -> dict:
        path = f"/riot/account/v1/accounts/by-riot-id/{quote(game_name, safe='')}/{quote(tag_line, safe='')}"
        return await self._get(region, path)

    async def match_ids(self, region: str, puuid: str, start_time: int | None = None, count: int = 20) -> list[str]:
        params: dict = {"count": count}
        if start_time is not None:
            params["startTime"] = start_time
        return await self._get(region, f"/lol/match/v5/matches/by-puuid/{puuid}/ids", params)

    async def match(self, region: str, match_id: str) -> dict:
        return await self._get(region, f"/lol/match/v5/matches/{match_id}")

    async def platform_status(self, platform: str = "na1") -> dict:
        return await self._get(platform, "/lol/status/v4/platform-data")


def _error_message(res: httpx.Response) -> str:
    known = {
        400: "Bad request to the Riot API",
        401: "Riot API key missing or invalid",
        403: "Riot API key rejected (development keys expire every 24 hours)",
        404: "Not found on the Riot API",
    }
    try:
        detail = res.json().get("status", {}).get("message")
    except ValueError:
        detail = None
    base = known.get(res.status_code, f"Riot API error {res.status_code}")
    return f"{base}: {detail}" if detail and res.status_code != 403 else base


_shared_limiter = RateLimiter()
