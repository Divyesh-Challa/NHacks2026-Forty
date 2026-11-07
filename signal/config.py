"""Loads [signal] from config/relay.toml and BACKEND_WS_URL from .env."""

import os
import tomllib
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

with open(ROOT / "config" / "relay.toml", "rb") as f:
    _TOML = tomllib.load(f)
SIGNAL = _TOML["signal"]
SYNTHETIC = _TOML["synthetic"]

BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8000/ws/signal")
