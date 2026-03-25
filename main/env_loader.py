from __future__ import annotations

import os
import re
from pathlib import Path


ENV_ASSIGNMENT_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = ENV_ASSIGNMENT_RE.match(line)
        if not match:
            continue

        key, value = match.groups()
        os.environ.setdefault(key, _strip_matching_quotes(value.strip()))

    return True


def get_default_env_file() -> Path:
    configured_path = os.environ.get("DJANGO_ENV_FILE") or os.environ.get("PYTHONANYWHERE_ENV_FILE")
    if configured_path:
        return Path(configured_path).expanduser()

    return Path(__file__).resolve().parent.parent / ".pythonanywhere.env"


def load_default_env_file() -> bool:
    return load_env_file(get_default_env_file())
