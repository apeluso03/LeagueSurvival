"""Random draw logic for spins (SPEC 7.1). Pure functions, no DB access."""

import random
from collections.abc import Sequence

MIN_PLAYERS = 2
MAX_PLAYERS = 5
ALLOWED_OPTIONS = (3, 4)


class SpinBlocked(Exception):
    """Raised when there are fewer alive champions than players."""


def effective_options(alive_count: int, n_players: int, requested: int) -> int:
    """How many options each player gets. Shrinks evenly when the pool is small; 0 means blocked."""
    if n_players <= 0:
        return 0
    return max(0, min(requested, alive_count // n_players))


def draw(
    alive_ids: Sequence[str],
    n_players: int,
    options_per_player: int,
    rng: random.Random | None = None,
) -> list[list[str]]:
    """Draw ordered option lists for each player, without replacement across all players."""
    if not MIN_PLAYERS <= n_players <= MAX_PLAYERS:
        raise ValueError(f"A spin needs {MIN_PLAYERS} to {MAX_PLAYERS} players, got {n_players}")
    if options_per_player not in ALLOWED_OPTIONS:
        raise ValueError(f"options_per_player must be one of {ALLOWED_OPTIONS}")

    unique_alive = list(dict.fromkeys(alive_ids))
    n = effective_options(len(unique_alive), n_players, options_per_player)
    if n == 0:
        raise SpinBlocked(
            f"Only {len(unique_alive)} champion(s) alive for {n_players} players. "
            "Use revive tokens or end the run."
        )

    picked = (rng or random.SystemRandom()).sample(unique_alive, n * n_players)
    return [picked[i * n : (i + 1) * n] for i in range(n_players)]
