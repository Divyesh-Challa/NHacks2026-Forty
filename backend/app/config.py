"""Loads config/relay.toml and .env. Import `settings` everywhere; don't hard-code tunables."""

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

with open(ROOT / "config" / "relay.toml", "rb") as f:
    TOML = tomllib.load(f)

INPUT = TOML["input"]
UI = TOML["ui"]
PREDICT = TOML["predict"]

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-5-5")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me-in-dotenv-32b")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'backend' / 'relay.db'}")
DEMO_CAREGIVER_PASSWORD = os.getenv("DEMO_CAREGIVER_PASSWORD", "relay-demo")
