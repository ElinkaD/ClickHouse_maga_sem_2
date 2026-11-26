"""Read the single project configuration file, with container environment overrides."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def setting(name: str) -> str:
    if name in os.environ:
        return os.environ[name]
    env_path = ROOT / ".env.local"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                if key.strip() == name:
                    return value.strip().strip('"').strip("'")
    raise RuntimeError(f"Missing {name} in .env.local or environment")
