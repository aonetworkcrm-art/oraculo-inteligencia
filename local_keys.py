"""
╔══════════════════════════════════════════════════════════════╗
║  LOCAL API KEYS — ONLY from environment variables           ║
║  Keys are read from .env file or system environment         ║
║  NO hardcoded keys — set them in .env or system env vars   ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import logging

logger = logging.getLogger("LocalKeys")

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        logger.debug(f"Loaded environment from: {dotenv_path}")
except ImportError:
    pass

# ─── API Keys (from env var ONLY — no hardcoded fallbacks) ───

def get_shodan_key() -> str:
    return os.environ.get("SHODAN_API_KEY", "")

def get_hunter_key() -> str:
    return os.environ.get("HUNTER_API_KEY", "")

def get_hibp_key() -> str:
    return os.environ.get("HIBP_API_KEY", "")

def get_vt_key() -> str:
    return os.environ.get("VT_API_KEY", "")

def get_censys_token() -> str:
    return os.environ.get("CENSYS_TOKEN", "")
