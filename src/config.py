"""Configuration and path handling for the PM4 pilot prototype."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def path(*parts: str) -> Path:
    p = ROOT.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and paste your key "
            "from https://aistudio.google.com/apikey."
        )
    return key


def model_name() -> str:
    return os.getenv("PM4_MODEL") or load_config()["generation"]["model"]


def log_salt() -> str:
    return os.getenv("PM4_LOG_SALT", "pm4-default-salt")
