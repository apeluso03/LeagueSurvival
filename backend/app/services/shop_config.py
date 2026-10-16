"""Per-run shop settings (SPEC 7.7 to 7.9). Runs store only their overrides; everything else
comes from DEFAULTS, so tuning a default later reaches every run that didn't change it."""

import copy

DEFAULTS: dict = {
    "prices": {"reroll": 250, "blacklist": 250, "swap": 300, "shield": 700, "choose": 1600, "contract": 100},
    "gold": {
        "kill": 10,
        "assist": 2,
        "damage_step": 5000,  # gold per full step of damage
        "damage_gold": 10,
        "vision_step": 10,
        "vision_gold": 5,
        "double": 25,
        "triple": 50,
        "quadra": 75,
        "penta": 100,
        # "stack": every multikill counter Riot reports pays out (Open Question 7).
        # "highest": a penta pays only the penta bonus, not the quadra/triple/double inside it.
        "multikill_mode": "stack",
    },
    "contract": {"payout": 300, "kills": 8, "assists": 15, "rating": "A+"},
    "blacklist_pct": 0.05,
}

ITEM_TYPES = ("reroll", "blacklist", "swap", "shield", "choose", "contract")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def effective(overrides: dict | None) -> dict:
    return _merge(DEFAULTS, overrides or {})


def validate_patch(patch: dict) -> dict:
    """Only known keys with sane values; returns the cleaned patch."""
    clean: dict = {}
    for section, values in patch.items():
        if section == "blacklist_pct":
            if not isinstance(values, (int, float)) or not 0 < values <= 0.5:
                raise ValueError("blacklist_pct must be between 0 and 0.5")
            clean[section] = float(values)
            continue
        if section not in DEFAULTS or not isinstance(values, dict):
            raise ValueError(f"Unknown setting: {section}")
        clean[section] = {}
        for key, value in values.items():
            if key not in DEFAULTS[section]:
                raise ValueError(f"Unknown setting: {section}.{key}")
            default = DEFAULTS[section][key]
            if isinstance(default, str):
                if not isinstance(value, str):
                    raise ValueError(f"{section}.{key} must be text")
                if key == "multikill_mode" and value not in ("stack", "highest"):
                    raise ValueError("multikill_mode must be 'stack' or 'highest'")
            elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{section}.{key} must be a whole number of 0 or more")
            if key in ("damage_step", "vision_step") and value == 0:
                raise ValueError(f"{section}.{key} must be more than 0")
            clean[section][key] = value
    return clean
