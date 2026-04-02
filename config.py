import json
import os

CONFIG_PATH = os.path.expanduser("~/.config/whisper-dictation/config.json")

DEFAULTS = {
    "hotkey": "<cmd>+<shift>+<space>",
    "model": "base",
    "language": None,  # None = auto-detect
}


def load() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        return {**DEFAULTS, **data}
    return dict(DEFAULTS)


def save(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
