"""
╔══════════════════════════════════════════════════╗
║  LOCAL API KEYS — Fallback when env vars unset  ║
║  Keys are read from here OR from env variables  ║
╚══════════════════════════════════════════════════╝
"""
import os

# ─── API Keys (fallback: env var → local config) ───

def get_shodan_key() -> str:
    return os.environ.get("SHODAN_API_KEY") or "zCPAWz4QwkW4q2yzcV9BgAZvn7EJEiqa"

def get_hunter_key() -> str:
    return os.environ.get("HUNTER_API_KEY") or "db75fb807a06e1ea30c587486bac714f04e8c577"

def get_hibp_key() -> str:
    return os.environ.get("HIBP_API_KEY") or ""

def get_vt_key() -> str:
    return os.environ.get("VT_API_KEY") or "14b83632f00c8b3788b43ec242fd3d53aa2ea18fa7bc6273d853d8f5194f1a76"

def get_censys_token() -> str:
    return os.environ.get("CENSYS_TOKEN") or "censys_UoywcT2S_GtS4BectMVyDhQwZgNmbZRq"
