"""Paths, config loading and small JSON helpers shared by every phase."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import truststore
import yaml

# Python 3.13+ rejects a corporate TLS-inspection CA unless we use the OS trust store. Every module imports
# this one, so every network call (feeds, LLM, SMTP) gets it.
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PROMPTS = Path(__file__).resolve().parent / "prompts"

# Editions are dated in IST (the run fires at 06:00 IST). Fixed offset avoids needing tzdata on Windows.
IST = timezone(timedelta(hours=5, minutes=30))


def load_config(path=ROOT / "config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def today_ist():
    return datetime.now(IST).date().isoformat()


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def load_prompt(name):
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
