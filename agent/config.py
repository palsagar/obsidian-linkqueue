"""Agent config: one env-format file, loaded explicitly so interactive and
launchd runs share it. Default location: ~/.config/linkqueue/agent.env."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path("~/.config/linkqueue/agent.env").expanduser()
REQUIRED = [
    "OPENROUTER_API_KEY",
    "QUEUE_URL",
    "CF_ACCESS_CLIENT_ID",
    "CF_ACCESS_CLIENT_SECRET",
    "VAULT_PATH",
]


@dataclass
class Config:
    openrouter_api_key: str
    queue_url: str
    cf_access_client_id: str
    cf_access_client_secret: str
    vault_path: Path
    model: str = "x-ai/grok-4.5"
    fallback_model: str = "deepseek/deepseek-v4-pro"
    limit: int = 20


def load_config(path: Path = DEFAULT_PATH) -> Config:
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")

    missing = [k for k in REQUIRED if not values.get(k)]
    if missing:
        raise ValueError(f"{path}: missing required keys: {', '.join(missing)}")

    return Config(
        openrouter_api_key=values["OPENROUTER_API_KEY"],
        queue_url=values["QUEUE_URL"],
        cf_access_client_id=values["CF_ACCESS_CLIENT_ID"],
        cf_access_client_secret=values["CF_ACCESS_CLIENT_SECRET"],
        vault_path=Path(os.path.expandvars(values["VAULT_PATH"])).expanduser(),
        model=values.get("TRIAGE_MODEL", Config.model),
        fallback_model=values.get("TRIAGE_FALLBACK_MODEL", Config.fallback_model),
        limit=int(values.get("TRIAGE_LIMIT", Config.limit)),
    )
