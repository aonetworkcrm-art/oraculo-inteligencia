"""
╔══════════════════════════════════════════════════════════════╗
║  DUMP FINDER ENGINE — Buscador de Bases de Datos Filtradas  ║
║                                                              ║
║  Dado un keyword + rango de fechas:                          ║
║  1. Busca URLs con bases de datos filtradas (dorking)        ║
║  2. Extrae email:pass combos con ComboParser                 ║
║  3. Filtra por fecha (año, mes, rango)                      ║
║  4. Guarda en: data/{keyword}/{año}/{mes}/                   ║
║                                                              ║
║  Inspirado en Joker Combo Leecher v1.0 y Hacku Dumper,      ║
║  pero open source, sin malware, y 100% desplegable.          ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus, unquote

import requests

from combo_leecher_engine import ComboParser, ComboEntry, ProxyManager, random_ua

# ═══════════════════════════════════════════════════════════════
#  TOR PROXY — for .onion and deep web access
# ═══════════════════════════════════════════════════════════════

# Default Tor SOCKS5 proxy (install Tor Browser or tor service)
TOR_PROXY = os.environ.get("TOR_PROXY", "socks5h://127.0.0.1:9050")
TOR_AVAILABLE = False

def _check_tor():
    """Check if Tor proxy is reachable."""
    global TOR_AVAILABLE
    try:
        r = requests.get("http://check.torproject.org/", proxies={"http": TOR_PROXY, "https": TOR_PROXY}, timeout=5)
        TOR_AVAILABLE = "Congratulations" in r.text or "Your IP" in r.text
    except Exception:
        TOR_AVAILABLE = False
    return TOR_AVAILABLE

def _tor_session():
    """Create a requests Session routed through Tor."""
    s = requests.Session()
    s.proxies = {"http": TOR_PROXY, "https": TOR_PROXY}
    return s

# Tor detection is lazy — only checked when actually needed (fetching .onion URLs)

logger = logging.getLogger("DumpFinder")

# ═══════════════════════════════════════════════════════════════
#  DORK TEMPLATES — find leaked credential URLs
# ═══════════════════════════════════════════════════════════════

DUMP_DORKS = [
    # ── Paste sites ──
    {"name": "pastebin_dump",  "dork": "site:pastebin.com \"{keyword}\" (\"email:pass\" OR \"password\" OR \"combo\" OR \"dump\" OR \"leak\")"},
    {"name": "pastebin_raw",   "dork": "site:pastebin.com/raw \"{keyword}\" (\"@\" OR \"pass\" OR \"login\")"},
    {"name": "rentry_dump",    "dork": "site:rentry.co \"{keyword}\" (\"email:pass\" OR \"combo\" OR \"dump\")"},
    {"name": "ghostbin_dump",  "dork": "site:ghostbin.co \"{keyword}\" (\"email\" OR \"password\" OR \"login\")"},
    {"name": "paste_ee",       "dork": "site:paste.ee \"{keyword}\" (\"email:pass\" OR \"password\" OR \"login\")"},
    {"name": "paste_gg",       "dork": "site:paste.gg \"{keyword}\" (\"email\" OR \"password\" OR \"combo\")"},

    # ── File types with credentials ──
    {"name": "txt_creds",      "dork": "filetype:txt \"{keyword}\" \"email\" \"password\" -sample -example"},
    {"name": "sql_export",     "dork": "filetype:sql \"{keyword}\" (\"INSERT INTO\" OR \"VALUES\") (\"email\" OR \"password\")"},
    {"name": "csv_creds",      "dork": "filetype:csv \"{keyword}\" \"email\" \"password\" -sample"},
    {"name": "xls_creds",      "dork": "filetype:xls \"{keyword}\" \"email\" \"password\" -sample"},
    {"name": "log_dump",       "dork": "filetype:log \"{keyword}\" (\"password\" OR \"login\" OR \"email\")"},
    {"name": "json_creds",     "dork": "filetype:json \"{keyword}\" (\"email\" OR \"password\" OR \"credentials\")"},
    {"name": "xml_creds",      "dork": "filetype:xml \"{keyword}\" (\"email\" OR \"password\" OR \"user\")"},

    # ── Exposed directories ──
    {"name": "index_of_creds", "dork": "intitle:\"index of\" \"{keyword}\" (\"credentials\" OR \"password\" OR \"backup\")"},
    {"name": "index_of_db",    "dork": "intitle:\"index of\" \"{keyword}\" (\"database\" OR \"sql\" OR \"dump\")"},
    {"name": "dir_listing",    "dork": "inurl:\"{keyword}\" intitle:\"index of\" (\"pass\" OR \"cred\" OR \"user\")"},

    # ── Combo-specific ──
    {"name": "combolist",      "dork": "\"{keyword} combo\" (\"email:pass\" OR \"user:pass\" OR \"combolist\")"},
    {"name": "leaked_db",      "dork": "\"{keyword}\" (\"leaked database\" OR \"leak dump\" OR \"breach\")"},
    {"name": "credential_dump","dork": "\"{keyword}\" \"credential dump\" filetype:txt"},
    {"name": "password_dump",  "dork": "\"{keyword}\" \"password dump\" filetype:txt"},

    # ── Telegram channels ──
    {"name": "telegram_leak",  "dork": "site:t.me \"{keyword}\" (\"combo\" OR \"leak\" OR \"dump\" OR \"email:pass\")"},
    {"name": "telegram_creds", "dork": "site:t.me \"{keyword}\" (\"password\" OR \"credentials\" OR \"login\")"},

    # ── Forums / leak sites ──
    {"name": "nulled_dump",    "dork": "site:nulled.to \"{keyword}\" (\"leak\" OR \"dump\" OR \"combo\" OR \"credentials\")"},
    {"name": "cracked_dump",   "dork": "site:cracked.to \"{keyword}\" (\"leak\" OR \"dump\" OR \"combo\")"},
    {"name": "leakzone_dump",  "dork": "site:leakzone.xyz \"{keyword}\" (\"leak\" OR \"dump\" OR \"combo\")"},
    {"name": "hackforums",     "dork": "site:hackforums.net \"{keyword}\" (\"leak\" OR \"dump\" OR \"combo\" OR \"credentials\")"},

    # ── GitHub / code repos ──
    {"name": "github_creds",   "dork": "site:github.com \"{keyword}\" (\"password\" OR \"credentials\" OR \"secret\")"},
    {"name": "github_dump",    "dork": "site:github.com \"{keyword}\" \"dump\" (\"email\" OR \"password\")"},

    # ── Additional paste sites ──
    {"name": "paste_fosshub",  "dork": "site:paste.fosshub.com \"{keyword}\" (\"email\" OR \"pass\" OR \"login\")"},
    {"name": "paste_centos",   "dork": "site:paste.centos.org \"{keyword}\" (\"email\" OR \"pass\")"},
    {"name": "paste_debian",   "dork": "site:paste.debian.net \"{keyword}\" (\"email\" OR \"password\")"},
    {"name": "dpaste_dump",    "dork": "site:dpaste.org \"{keyword}\" (\"email\" OR \"password\" OR \"login\")"},
    {"name": "pastebin_archive","dork": "site:pastebin.com \"{keyword}\" \"password\" \"@\" -\".com\" -\"<\" -\">\""},

    # ── Open directories with credentials ──
    {"name": "open_ftp",       "dork": "intitle:\"index of\" \"{keyword}\" ftp (\"pass\" OR \"cred\" OR \"user\")"},
    {"name": "backup_files",   "dork": "filetype:bak \"{keyword}\" (\"password\" OR \"email\" OR \"user\")"},
    {"name": "env_files",      "dork": "filetype:env \"{keyword}\" (\"password\" OR \"api\" OR \"secret\")"},
    {"name": "config_exposed", "dork": "filetype:conf \"{keyword}\" (\"password\" OR \"pass\" OR \"user\")"},

    # ── Discord ──
    {"name": "discord_dump",   "dork": "site:discord.com/channels \"{keyword}\" (\"combo\" OR \"dump\" OR \"leak\" OR \"password\")"},
    {"name": "discord_gg",     "dork": "site:discord.gg \"{keyword}\" (\"combo\" OR \"leak\" OR \"password\")"},

    # ── Deep Web: .onion (Tor) ──
    {"name": "onion_paste",    "dork": "site:pastebin.com \"{keyword}\" \".onion\" (\"combo\" OR \"leak\" OR \"dump\" OR \"creds\")"},
    {"name": "onion_forum",    "dork": "site:pastebin.com \"{keyword}\" \"onion\" (\"forum\" OR \"market\" OR \"shop\" OR \"exchange\")"},
    {"name": "onion_creds",    "dork": "inurl:\"{keyword}\" \".onion\" (\"email\" OR \"password\" OR \"login\" OR \"credentials\")"},
    {"name": "onion_dump",     "dork": "filetype:txt \"{keyword}\" \".onion\" (\"dump\" OR \"leak\" OR \"combolist\")"},
    {"name": "onion_db",       "dork": "\"{keyword}\" \".onion\" (\"database\" OR \"sql\" OR \"mysql\" OR \"dump\")"},
    {"name": "onion_breach",   "dork": "\"{keyword}\" \".onion\" (\"breach\" OR \"leak\" OR \"leaked\" OR \"compromised\")"},

    # ── Deep Web: .i2p ──
    {"name": "i2p_sites",      "dork": "inurl:\"{keyword}\" \".i2p\" (\"forum\" OR \"market\" OR \"creds\" OR \"login\")"},
    {"name": "i2p_creds",      "dork": "\"{keyword}\" \".i2p\" (\"password\" OR \"credentials\" OR \"database\" OR \"dump\")"},

    # ── Deep Web: general hidden services ──
    {"name": "hidden_service",  "dork": "inurl:\"{keyword}\" (\"hidden\" OR \"tor\" OR \"onion\") (\"email:pass\" OR \"combo\" OR \"leak\" OR \"dump\")"},
    {"name": "tor_exit_nodes",  "dork": "inurl:\"{keyword}\" \"tor exit\" (\"log\" OR \"credentials\" OR \"password\" OR \"capture\")"},
]

# ═══════════════════════════════════════════════════════════════
#  STEALTH HELPERS — anti-detection para dorking
# ═══════════════════════════════════════════════════════════════

_USER_AGENTS = [
    # Chrome 120+ Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    # Chrome macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/122.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

_REFERERS = [
    "https://www.google.com/",
    "https://search.yahoo.com/",
    "https://www.bing.com/",
    "https://duckduckgo.com/",
    "https://t.co/",
    "https://www.facebook.com/",
    "https://www.reddit.com/",
]

_ACCEPT_LANGS = ["es-US,es;q=0.9,en;q=0.8", "en-US,en;q=0.9,es;q=0.8", "es-ES,es;q=0.9,en;q=0.7"]

def _stealth_headers():
    """Generate stealth HTTP headers to avoid detection."""
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": random.choice(_ACCEPT_LANGS),
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": random.choice(_REFERERS),
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

def _random_delay(min_s: float = 0.5, max_s: float = 3.0):
    """Random delay to avoid rate limiting."""
    time.sleep(random.uniform(min_s, max_s))


# ═══════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════

class _RateLimiter:
    """Rate limiter for API calls."""
    def __init__(self, requests_per_minute: int = 30):
        self.interval = 60.0 / max(requests_per_minute, 1)
        self._last_calls: dict = {}
    def wait(self, source: str = "default"):
        last = self._last_calls.get(source, 0.0)
        elapsed = time.time() - last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last_calls[source] = time.time()


# ═══════════════════════════════════════════════════════════════
#  PASTE DIRECT SCRAPER — busca dumps directamente SIN Google
# ═══════════════════════════════════════════════════════════════

class PasteDirectScraper:
    """
    Scrape paste sites DIRECTLY for keyword matches.
    No search engines needed — queries each site natively.
    """

    # Direct paste site scraping (bypasses search engines entirely)
    PASTEBIN_RAW = "https://pastebin.com/raw/"
    # Archived.today mirror for pastebin archives
    ARCHIVE_URLS = [
        "https://archive.is/search/?q=pastebin.com+{keyword}",
        "https://cachedview.nl/search?q=pastebin.com+{keyword}+email%3Apass",
    ]

    def __init__(self):
        self.session = requests.Session()
        self.rate_limiter = _RateLimiter(requests_per_minute=20)
        self.proxy_mgr = ProxyManager()

    def search_pastebin_recent(self, keyword: str, max_results: int = 20) -> List[Dict[str, str]]:
        """
        Find pastebin raw URLs using DuckDuckGo (no CAPTCHA).
        Searches for recent pastebin posts matching keyword.
        """
        self.rate_limiter.wait(source="pastebin_search")
        encoded = quote_plus(keyword)
        url = f"https://lite.duckduckgo.com/lite/?q=site:pastebin.com+%22{encoded}%22+%28email%3Apass+OR+password+OR+combo%29"

        try:
            self.session.headers.update(_stealth_headers())
            proxy = self.proxy_mgr.get_random()
            resp = self.session.get(url, timeout=8, proxies=proxy)
            if resp.status_code != 200:
                return []

            results = []
            seen = set()
            # Extract any http/https links from DDG lite results
            for match in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>', resp.text):
                url_val = match.group(1)
                if url_val in seen:
                    continue
                seen.add(url_val)
                # Filter to pastebin URLs
                if "pastebin.com" in url_val:
                    # Convert to raw format
                    if "/raw/" not in url_val:
                        paste_id_match = re.search(r'pastebin\.com/([a-zA-Z0-9]+)', url_val)
                        if paste_id_match:
                            url_val = f"https://pastebin.com/raw/{paste_id_match.group(1)}"
                    results.append({"url": url_val, "title": f"Pastebin: {keyword}", "snippet": "", "dork_name": "pastebin_direct"})
                    if len(results) >= max_results:
                        break
            return results
        except Exception as e:
            logger.debug(f"Pastebin search error: {e}")
            return []

    def search_archives(self, keyword: str, max_results: int = 10) -> List[Dict[str, str]]:
        """Search archive/aggregator sites for keyword-related content."""
        results = []
        seen = set()
        encoded = quote_plus(keyword)

        for arch_url in self.ARCHIVE_URLS:
            self.rate_limiter.wait(source="archive")
            url = arch_url.replace("{keyword}", encoded)
            try:
                self.session.headers.update(_stealth_headers())
                proxy = self.proxy_mgr.get_random()
                resp = self.session.get(url, timeout=8, proxies=proxy)
                if resp.status_code != 200:
                    continue
                for match in re.finditer(r'href="(https?://[^"]+)"[^>]*>', resp.text):
                    url_val = match.group(1)
                    if url_val not in seen and "http" in url_val:
                        seen.add(url_val)
                        results.append({"url": url_val, "title": f"Archive: {keyword}", "snippet": "", "dork_name": "archive_search"})
                        if len(results) >= max_results:
                            break
            except Exception as e:
                logger.debug(f"Archive search error: {e}")

        return results

    def search_all(self, keyword: str, max_per_source: int = 5) -> List[Dict[str, str]]:
        """
        Search ALL direct sources for keyword.
        Bypasses Google/Bing entirely — uses DuckDuckGo + archives.
        """
        all_urls = []
        seen = set()

        # 1. Pastebin via DuckDuckGo
        pastebin_urls = self.search_pastebin_recent(keyword, max_results=max_per_source * 2)
        for u in pastebin_urls:
            if u["url"] not in seen:
                seen.add(u["url"])
                all_urls.append(u)

        _random_delay(0.5, 1.5)

        # 2. Archive sites
        archive_urls = self.search_archives(keyword, max_results=max_per_source)
        for u in archive_urls:
            if u["url"] not in seen:
                seen.add(u["url"])
                all_urls.append(u)

        return all_urls


# ═══════════════════════════════════════════════════════════════
#  DORK ENGINE — Google + Bing + DuckDuckGo with stealth
# ═══════════════════════════════════════════════════════════════

class DorkEngine:
    """Execute dork queries against search engines with maximum stealth."""

    def __init__(self):
        self.session = requests.Session()
        self.rate_limiter = _RateLimiter(requests_per_minute=8)
        self.proxy_mgr = ProxyManager()

    def search(self, dork: str, max_results: int = 10) -> List[Dict[str, str]]:
        """
        Execute a dork query against multiple search engines.
        Order: DuckDuckGo (no CAPTCHA) → Google → Bing
        """
        encoded = quote_plus(dork)

        # ── 1. DuckDuckGo (no CAPTCHA, no blocking) ──
        try:
            results = self._search_duckduckgo(encoded, max_results)
            if results:
                return results
        except Exception as e:
            logger.debug(f"DuckDuckGo failed: {e}")

        _random_delay(0.5, 2.0)

        # ── 2. Google ──
        try:
            results = self._search_google(encoded, max_results)
            if results:
                return results
        except Exception as e:
            logger.debug(f"Google failed: {e}")

        _random_delay(0.5, 2.0)

        # ── 3. Bing ──
        try:
            results = self._search_bing(encoded, max_results)
        except Exception as e:
            logger.debug(f"Bing failed: {e}")

        return results

    def _stealth_get(self, url: str, timeout: int = 8) -> Optional[requests.Response]:
        """HTTP GET with full stealth headers + proxy rotation."""
        self.session.headers.update(_stealth_headers())
        proxy = self.proxy_mgr.get_random()
        try:
            return self.session.get(url, timeout=timeout, proxies=proxy)
        except Exception:
            return None

    def _search_duckduckgo(self, encoded_dork: str, max_results: int) -> List[Dict[str, str]]:
        """
        Search DuckDuckGo — no CAPTCHA, no blocks.
        Uses the lite (non-JS) version for easy scraping.
        """
        self.rate_limiter.wait(source="duckduckgo")
        results = []
        url = f"https://lite.duckduckgo.com/lite/?q={encoded_dork}"

        resp = self._stealth_get(url)
        if not resp or resp.status_code != 200:
            return results

        # Parse DDG lite HTML
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")
            # DDG lite uses table-based layout
            for link in soup.select("a")[:max_results * 2]:
                href = link.get("href", "")
                if not href.startswith("http"):
                    continue
                title = link.get_text(strip=True) or ""
                if not title:
                    continue
                # Skip DDG internal links
                if any(x in href for x in ["duckduckgo.com", "safe.duckduckgo.com"]):
                    continue
                results.append({"url": href, "title": title, "snippet": ""})
                if len(results) >= max_results:
                    break
        except Exception:
            pass            # Also try html version (more results)
        if not results:
            try:
                url2 = f"https://html.duckduckgo.com/html/?q={encoded_dork}"
                self.rate_limiter.wait(source="duckduckgo_html")
                resp2 = self._stealth_get(url2)
                if resp2 and resp2.status_code == 200:
                    soup2 = BeautifulSoup(resp2.text, "html.parser")
                    for result in soup2.select(".result__body")[:max_results]:
                        link_el = result.select_one(".result__a")
                        if not link_el:
                            continue
                        href = link_el.get("href", "")
                        if not href.startswith("http"):
                            continue
                        href_clean = href.split("uddg=")[-1].split("&")[0] if "uddg=" in href else href
                        href_clean = unquote(href_clean)
                        title = link_el.get_text(strip=True) or ""
                        results.append({"url": href_clean, "title": title, "snippet": ""})
                        if len(results) >= max_results:
                            break
            except Exception:
                pass

        return results

    def _search_google(self, encoded_dork: str, max_results: int) -> List[Dict[str, str]]:
        """Search Google with stealth + fallbacks."""
        self.rate_limiter.wait(source="google")
        url = f"https://www.google.com/search?q={encoded_dork}&num={min(max_results, 20)}"

        resp = self._stealth_get(url)
        if not resp:
            return []
        if resp.status_code != 200 and resp.status_code != 429:
            return self._extract_urls_regex(resp.text, max_results) if resp.text else []

        # Detect CAPTCHA/block
        text_lower = resp.text.lower()
        if any(x in text_lower for x in ["unusual traffic", "captcha", "please verify", "rate limit"]):
            logger.debug(f"Google blocked (CAPTCHA)")
            return self._extract_urls_regex(resp.text, max_results) if resp.status_code == 200 else []

        # BS4 parse
        results = self._parse_google_bs4(resp.text, max_results)
        if results:
            return results

        # Regex fallback
        return self._extract_urls_regex(resp.text, max_results)

    def _parse_google_bs4(self, html: str, max_results: int) -> List[Dict[str, str]]:
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for g in soup.select("div.g")[:max_results]:
                link_el = g.select_one("a")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if href.startswith("/url?q="):
                    href = href.split("/url?q=")[1].split("&")[0]
                if not href or "http" not in href:
                    continue
                title_el = g.select_one("h3")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet_el = g.select_one("div.VwiC3b")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append({"url": href, "title": title, "snippet": snippet})
        except Exception:
            pass
        return results

    def _search_bing(self, encoded_dork: str, max_results: int) -> List[Dict[str, str]]:
        """Search Bing with stealth."""
        self.rate_limiter.wait(source="bing")
        url = f"https://www.bing.com/search?q={encoded_dork}&count={min(max_results, 20)}"

        resp = self._stealth_get(url)
        if not resp or resp.status_code != 200:
            return []

        # BS4
        results = self._parse_bing_bs4(resp.text, max_results)
        if results:
            return results

        # Regex fallback
        return self._extract_urls_regex(resp.text, max_results)

    def _parse_bing_bs4(self, html: str, max_results: int) -> List[Dict[str, str]]:
        results = []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for li in soup.select("li.b_algo")[:max_results]:
                link_el = li.select_one("a")
                if not link_el:
                    continue
                href = link_el.get("href", "")
                if not href or "http" not in href:
                    continue
                title_el = li.select_one("h2")
                title = title_el.get_text(strip=True) if title_el else ""
                snippet_el = li.select_one(".b_caption p")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                results.append({"url": href, "title": title, "snippet": snippet})
        except Exception:
            pass
        return results

    @staticmethod
    def _extract_urls_regex(html: str, max_results: int) -> List[Dict[str, str]]:
        """Extract URLs from HTML using regex fallback."""
        results = []
        seen = set()
        pattern = r'<a[^>]*href="(https?://[^"\s]+)"[^>]*>(.*?)</a>'
        for match in re.finditer(pattern, html, re.IGNORECASE | re.DOTALL):
            url = match.group(1)
            if url in seen:
                continue
            seen.add(url)
            if any(x in url for x in ["google.com/search", "accounts.google", "policies.google", "support.google"]):
                continue
            title = re.sub(r'<[^>]+>', '', match.group(2)).strip()[:100]
            results.append({"url": url, "title": title, "snippet": ""})
            if len(results) >= max_results:
                break
        return results


# ═══════════════════════════════════════════════════════════════
#  FETCHER — download content from a URL with stealth
# ═══════════════════════════════════════════════════════════════

class URLFetcher:
    """Download content from URLs with stealth + retry."""

    def __init__(self):
        self.session = requests.Session()
        self.rate_limiter = _RateLimiter(requests_per_minute=12)
        self.proxy_mgr = ProxyManager()

    def fetch(self, url: str, timeout: int = 10, retries: int = 2) -> Optional[str]:
        """Fetch URL content with retry. Routes .onion/.i2p URLs through Tor."""
        is_onion = ".onion" in url.lower() or ".i2p" in url.lower()
        
        for attempt in range(retries + 1):
            self.rate_limiter.wait(source=f"fetch_{hash(url) % 100}")
            try:
                if is_onion:
                    # Check Tor availability lazily
                    if not TOR_AVAILABLE:
                        _check_tor()
                    if TOR_AVAILABLE:
                        tor_sess = _tor_session()
                        tor_sess.headers.update(_stealth_headers())
                        resp = tor_sess.get(url, timeout=timeout + 10, verify=False)
                    else:
                        logger.debug(f"Tor not available, skipping onion URL: {url[:50]}")
                        return None
                else:
                    self.session.headers.update(_stealth_headers())
                    proxy = self.proxy_mgr.get_random()
                    resp = self.session.get(url, timeout=timeout, proxies=proxy)
                
                if resp.status_code == 200 and len(resp.text) > 50:
                    return resp.text
            except Exception as e:
                logger.debug(f"Fetch attempt {attempt+1} error {url[:50]}: {e}")
                if attempt < retries:
                    _random_delay(1, 3)
        return None


# ═══════════════════════════════════════════════════════════════
#  DATE FILTER
# ═══════════════════════════════════════════════════════════════

class DateFilter:
    """Filters combos by date range (year, month, or custom range)."""

    @staticmethod
    def filter(combos: List[ComboEntry],
               year: Optional[int] = None,
               month: Optional[int] = None,
               date_from: Optional[str] = None,
               date_to: Optional[str] = None) -> List[ComboEntry]:
        """
        Filter combos by date criteria.
        - year: 2023, 2024, 2026, etc.
        - month: 1-12 (only when year is also specified)
        - date_from/date_to: ISO format "2023-01-01"
        """
        if not combos:
            return []

        filtered = []

        for combo in combos:
            discovered = combo.discovered_date or ""
            if not discovered:
                continue

            # Parse date
            try:
                parts = discovered.split("-")
                if len(parts) < 3:
                    continue
                combo_year = int(parts[0])
                combo_month = int(parts[1])
            except (ValueError, IndexError):
                continue

            # Filter by year
            if year is not None and combo_year != year:
                continue

            # Filter by month (only when year is specified)
            if month is not None and combo_month != month:
                continue

            # Filter by date range
            if date_from and discovered < date_from:
                continue
            if date_to and discovered > date_to:
                continue

            filtered.append(combo)

        return filtered


# ═══════════════════════════════════════════════════════════════
#  LOCAL SAVER — save combos to organized folders
# ═══════════════════════════════════════════════════════════════

class LocalSaver:
    """
    Save credential dumps to organized folder structure:
        data/{keyword}/{year}/{month}/{keyword}_{date}.txt
    """

    BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

    @classmethod
    def save_combos(cls, keyword: str, combos: List[ComboEntry],
                    year: Optional[int] = None,
                    month: Optional[int] = None) -> Dict[str, Any]:
        """
        Save combos to organized folder structure.
        Returns: { "files_created": [paths], "total_saved": int, "path": str }
        """
        if not combos:
            return {"files_created": [], "total_saved": 0, "path": ""}

        # Organize by date
        by_date: Dict[str, List[ComboEntry]] = {}
        for combo in combos:
            d = combo.discovered_date or "unknown"
            by_date.setdefault(d, []).append(combo)

        files_created = []
        total_saved = 0

        for date_str, date_combos in by_date.items():
            # Parse date parts
            try:
                parts = date_str.split("-")
                yr = parts[0]
                mo = parts[1]
            except (IndexError, ValueError):
                yr = "unknown"
                mo = "unknown"

            # Build folder path: data/{keyword}/{year}/{month}/
            folder = os.path.join(cls.BASE_PATH, keyword.lower(), yr, mo)
            os.makedirs(folder, exist_ok=True)

            # Build filename: {keyword}_{date}.txt
            safe_date = date_str.replace("-", "")
            filename = f"{keyword.lower()}_{safe_date}.txt"
            filepath = os.path.join(folder, filename)

            # Write email:pass format (one per line)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(f"# DumpFinder - {keyword} - {date_str}\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write(f"# Total combos: {len(date_combos)}\n")
                f.write("# Format: email:password\n\n")

                for combo in date_combos:
                    identifier = combo.email or combo.username or ""
                    if identifier and combo.password:
                        f.write(f"{identifier}:{combo.password}\n")
                        total_saved += 1

            files_created.append(filepath)

        # Also save a merged file with all combos for this keyword
        if combos:
            yr_str = str(year) if year else "all"
            mo_str = f"{month:02d}" if month else "all"
            merge_folder = os.path.join(cls.BASE_PATH, keyword.lower(), yr_str, mo_str)
            os.makedirs(merge_folder, exist_ok=True)
            merge_file = os.path.join(merge_folder, f"{keyword.lower()}_full_dump.txt")

            with open(merge_file, "w", encoding="utf-8") as f:
                f.write(f"# DumpFinder - {keyword} - FULL DUMP\n")
                f.write(f"# Generated: {datetime.now().isoformat()}\n")
                f.write(f"# Total combos: {len(combos)}\n")
                f.write(f"# Date range: {year or 'all'}-{month or 'all'}\n")
                f.write("# Format: email:password\n\n")

                for combo in combos:
                    identifier = combo.email or combo.username or ""
                    domain = combo.domain or ""
                    source = combo.source_type or ""
                    src_url = combo.source_url or ""
                    date = combo.discovered_date or ""
                    if identifier and combo.password:
                        f.write(f"{identifier}:{combo.password}  #{domain} | {source} | {date}\n")

            files_created.append(merge_file)

        return {
            "files_created": files_created,
            "total_saved": total_saved,
            "path": os.path.join(cls.BASE_PATH, keyword.lower()),
        }


# ═══════════════════════════════════════════════════════════════
#  MAIN DUMP FINDER ENGINE
# ═══════════════════════════════════════════════════════════════

class DumpFinder:
    """
    Main DumpFinder engine.
    
    Pipeline:
      1. Execute dork queries against search engines
      2. Fetch content from found URLs
      3. Parse email:pass combos using ComboParser
      4. Filter by date (year, month, range)
      5. Save to local folders
      6. Return results
    """

    def __init__(self):
        self.dork_engine = DorkEngine()
        self.paste_scraper = PasteDirectScraper()
        self.fetcher = URLFetcher()
        self.parser = ComboParser()
        self.date_filter = DateFilter()
        self.local_saver = LocalSaver()
        self.hunter_connector = None
        try:
            from intel_connectors import HunterConnector
            self.hunter_connector = HunterConnector()
        except Exception:
            self.hunter_connector = None

    def search(self,
               keyword: str,
               year: Optional[int] = None,
               month: Optional[int] = None,
               date_from: Optional[str] = None,
               date_to: Optional[str] = None,
               max_dorks: int = 15,
               max_fetches: int = 10,
               save_to_disk: bool = True) -> Dict[str, Any]:
        """
        Execute a complete dump search pipeline.

        Args:
            keyword: Search term (e.g., "comcast")
            year: Filter by year (e.g., 2023)
            month: Filter by month 1-12 (requires year)
            date_from: ISO date "2023-01-01"
            date_to: ISO date "2023-12-31"
            max_dorks: Max dork queries to execute
            max_fetches: Max URLs to fetch per dork
            save_to_disk: Save results to local folders

        Returns:
            Dict with: keyword, dorks_executed, urls_found, urls_fetched,
                      combos_found, filtered_combos, files_saved, stats
        """
        start_time = time.time()
        keyword = keyword.strip().lower()

        # ─── Step 1a: Execute dorks (Google + Bing + DuckDuckGo) ───
        all_urls = []
        dorks_run = []

        selected_dorks = random.sample(DUMP_DORKS, min(max_dorks, len(DUMP_DORKS)))

        for dork_spec in selected_dorks:
            dork_template = dork_spec["dork"].replace("{keyword}", keyword)
            dork_name = dork_spec["name"]

            try:
                urls = self.dork_engine.search(dork_template, max_results=5)
                for u in urls:
                    u["dork_name"] = dork_name
                all_urls.extend(urls)
                dorks_run.append(dork_name)
                logger.info(f"🔍 Dork '{dork_name}': {len(urls)} URLs")
            except Exception as e:
                logger.debug(f"Dork '{dork_name}' error: {e}")

            _random_delay(0.5, 2.0)

        # ─── Step 1b: Direct paste scraping (pastebin, rentry, ghostbin, etc.) ───
        logger.info("📋 Scraping paste sites directly for keyword...")
        try:
            paste_urls = self.paste_scraper.search_all(keyword, max_per_source=5)
            paste_seen = set()
            for u in paste_urls:
                if u["url"] not in paste_seen:
                    paste_seen.add(u["url"])
                    all_urls.append(u)
            logger.info(f"📋 Paste scraping: {len(paste_urls)} additional URLs")
        except Exception as e:
            logger.debug(f"Paste scraping error: {e}")

        # Deduplicate URLs
        seen_urls = set()
        unique_urls = []
        for u in all_urls:
            url = u.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_urls.append(u)
        all_urls = unique_urls

        logger.info(f"📡 Total unique URLs found: {len(all_urls)}")

        # ─── Step 1b: Fallback — use Hunter.io if dorking found nothing ───
        if not all_urls and self.hunter_connector and self.hunter_connector.enabled:
            logger.info(f"📧 Dorking returned no results — trying Hunter.io for real emails...")
            try:
                hs = self.hunter_connector.domain_search(keyword, limit=10)
                if hs.get("success") and hs.get("data", {}).get("emails"):
                    for email_info in hs["data"]["emails"]:
                        email = email_info.get("value", "")
                        if email and "@" in email:
                            domain = email.split("@")[1]
                            all_urls.append({
                                "url": f"https://{domain}",
                                "title": f"{email_info.get('position', 'Employee')} at {domain}",
                                "snippet": f"Email: {email} | {email_info.get('confidence', 0)}% confidence",
                                "dork_name": "hunter_io",
                            })
                    logger.info(f"📧 Hunter.io: {len(all_urls)} emails found for {keyword}")
            except Exception as e:
                logger.debug(f"Hunter.io fallback error: {e}")

        # ─── Step 2: Fetch content from found URLs ───
        raw_combos = []
        urls_fetched = 0
        fetch_errors = 0

        for url_info in all_urls[:max_fetches]:
            url = url_info.get("url", "")
            if not url:
                continue

            content = self.fetcher.fetch(url)
            if content:
                urls_fetched += 1
                # Parse combos from this URL
                combos = self.parser.parse_text(
                    content,
                    source_url=url,
                    source_type=url_info.get("dork_name", "dorking"),
                    keyword=keyword,
                )
                raw_combos.extend(combos)
                logger.info(f"📥 Fetched {url[:60]}... → {len(combos)} combos")
            else:
                fetch_errors += 1

        logger.info(f"📊 Total raw combos (pre-filter): {len(raw_combos)}")

        # ─── Step 3: Calculate date for each combo ───
        # Try to extract date from combo data or URLs
        now = datetime.now()
        for combo in raw_combos:
            if not combo.discovered_date:
                # Try to estimate from source URL or use today
                combo.discovered_date = now.strftime("%Y-%m-%d")
                combo.discovered_at = now.isoformat()

        # ─── Step 4: Filter by date ───
        filtered_combos = self.date_filter.filter(
            raw_combos,
            year=year,
            month=month,
            date_from=date_from,
            date_to=date_to,
        )

        # If no date filter, all combos pass
        if year is None and month is None and date_from is None and date_to is None:
            filtered_combos = raw_combos

        # Deduplicate final combos
        seen_final = set()
        unique_final = []
        for c in filtered_combos:
            key = f"{c.email.lower()}:{c.password}"
            if key not in seen_final:
                seen_final.add(key)
                unique_final.append(c)
        filtered_combos = unique_final

        logger.info(f"🎯 Filtered combos: {len(filtered_combos)} (from {len(raw_combos)} raw)")

        # ─── Step 5: Save to disk ───
        save_info = {"files_created": [], "total_saved": 0, "path": ""}
        if save_to_disk and filtered_combos:
            save_info = self.local_saver.save_combos(
                keyword, filtered_combos,
                year=year, month=month,
            )
            logger.info(f"💾 Saved to: {save_info.get('path', 'N/A')} ({save_info.get('total_saved', 0)} combos)")

        # ─── Build result ───
        elapsed = round(time.time() - start_time, 2)

        # Stats by source
        by_source = {}
        for c in filtered_combos:
            src = c.source_type or "unknown"
            by_source[src] = by_source.get(src, 0) + 1

        # Stats by type
        by_type = {}
        for c in filtered_combos:
            tp = c.record_type or "unknown"
            by_type[tp] = by_type.get(tp, 0) + 1

        # Stats by domain
        by_domain = {}
        for c in filtered_combos:
            dom = c.domain or "unknown"
            by_domain[dom] = by_domain.get(dom, 0) + 1

        # Top URLs found
        top_urls = []
        for u in all_urls[:20]:
            top_urls.append({
                "url": u.get("url", ""),
                "title": u.get("title", ""),
                "source": u.get("dork_name", ""),
            })

        return {
            "success": True,
            "keyword": keyword,
            "took_seconds": elapsed,
            "timestamp": datetime.now().isoformat(),
            "dorks_executed": len(dorks_run),
            "dorks_list": dorks_run[:20],
            "urls_found": len(all_urls),
            "urls_fetched": urls_fetched,
            "fetch_errors": fetch_errors,
            "combos_found": len(raw_combos),
            "filtered_combos_count": len(filtered_combos),
            "files_saved": save_info,
            "top_urls": top_urls,
            "stats": {
                "by_source": by_source,
                "by_type": by_type,
                "by_domain": dict(sorted(by_domain.items(), key=lambda x: -x[1])[:20]),
            },
            "combos_sample": [
                {
                    "email": c.email,
                    "password": c.password[:15] + "***" if len(c.password) > 15 else c.password,
                    "domain": c.domain,
                    "source": c.source_type,
                    "date": c.discovered_date,
                }
                for c in filtered_combos[:50]
            ],
            "date_filter": {
                "year": year,
                "month": month,
                "date_from": date_from,
                "date_to": date_to,
            },
        }


    def export(self,
                keyword: str,
                fmt: str = "txt",
                year: Optional[int] = None,
                month: Optional[int] = None,
                date_from: Optional[str] = None,
                date_to: Optional[str] = None,
                max_dorks: int = 15,
                max_fetches: int = 20) -> str:
        """
        Execute a search and export ALL filtered combos in the requested format.
        Unlike search() which returns only 50 sample combos, this returns everything.

        Args:
            keyword: Search term
            fmt: Export format — "txt", "csv", or "json"
            year: Filter by year
            month: Filter by month
            date_from: ISO date start
            date_to: ISO date end
            max_dorks: Max dork queries
            max_fetches: Max URLs to fetch (higher = more data)

        Returns:
            Formatted string in the requested format
        """
        result = self.search(
            keyword=keyword,
            year=year,
            month=month,
            date_from=date_from,
            date_to=date_to,
            max_dorks=max_dorks,
            max_fetches=max_fetches,
            save_to_disk=True,
        )

        combos = result.get("stats", {}).get("by_source", {})
        total = result.get("filtered_combos_count", 0)
        keyword_safe = keyword.strip().lower()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Re-hydrate full combos from the search result's file save
        # Try to load from the saved files first (they have ALL combos)
        full_combos = []
        files_saved = result.get("files_saved", {}).get("files_created", [])

        if files_saved:
            # Read full dump file
            full_dump_files = [f for f in files_saved if "full_dump" in f]
            if full_dump_files:
                try:
                    with open(full_dump_files[0], "r", encoding="utf-8") as fh:
                        content = fh.read()
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and "#" not in line and ":" in line:
                            parts = line.split(":", 1)
                            full_combos.append({
                                "email": parts[0].strip(),
                                "password": parts[1].split("  #")[0].strip() if "  #" in parts[1] else parts[1].strip(),
                            })
                except Exception:
                    pass

        # Fallback: use the combos_sample from the search result
        if not full_combos:
            full_combos = result.get("combos_sample", [])

        # ─── Format ───
        if fmt == "json":
            return json.dumps({
                "keyword": keyword_safe,
                "total": total,
                "exported": len(full_combos),
                "timestamp": timestamp,
                "combos": full_combos,
                "stats": result.get("stats", {}),
                "files_saved": files_saved,
            }, indent=2, ensure_ascii=False)

        elif fmt == "csv":
            lines = ["email,password,dominio,fuente,fecha"]
            for c in full_combos:
                email = c.get("email", "").replace('"', '""')
                pw = c.get("password", "").replace('"', '""')
                dom = c.get("domain", "").replace('"', '""')
                src = c.get("source", c.get("source_type", "")).replace('"', '""')
                dt = c.get("date", c.get("discovered_date", "")).replace('"', '""')
                lines.append(f'"{email}","{pw}","{dom}","{src}","{dt}"')
            return "\n".join(lines)

        else:  # txt
            header = (
                f"# DumpFinder Export - {keyword_safe}\n"
                f"# Generated: {timestamp}\n"
                f"# Total combos: {total}\n"
                f"# Export format: email:password\n\n"
            )
            body_lines = []
            for c in full_combos:
                identifier = c.get("email", "") or ""
                password = c.get("password", "") or ""
                date_str = c.get("date", c.get("discovered_date", ""))
                source_str = c.get("source", c.get("source_type", ""))
                domain_str = c.get("domain", "")
                if identifier and password:
                    comment = f"#{domain_str} | {source_str} | {date_str}"
                    body_lines.append(f"{identifier}:{password}  {comment}")
            return header + "\n".join(body_lines)



# ═══════════════════════════════════════════════════════════════
#  CLI TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "comcast"
    year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    month = int(sys.argv[3]) if len(sys.argv) > 3 else None

    print(f"\n🛸 DUMP FINDER v1.0")
    print(f"🔍 Keyword: {keyword}")
    print(f"📅 Year: {year or 'all'}  Month: {month or 'all'}")
    print(f"{'─' * 50}")

    finder = DumpFinder()
    result = finder.search(
        keyword=keyword,
        year=year,
        month=month,
        max_dorks=10,
        max_fetches=5,
        save_to_disk=True,
    )

    print(f"\n✅ RESULTS:")
    print(f"   Dorks executed: {result['dorks_executed']}")
    print(f"   URLs found: {result['urls_found']}")
    print(f"   URLs fetched: {result['urls_fetched']}")
    print(f"   Combos found: {result['combos_found']}")
    print(f"   After filter: {result['filtered_combos_count']}")
    print(f"   Time: {result['took_seconds']}s")

    if result.get("files_saved", {}).get("files_created"):
        print(f"\n📁 Files saved:")
        for f in result["files_saved"]["files_created"]:
            print(f"   📄 {f}")

    if result.get("top_urls"):
        print(f"\n🔗 Top URLs found:")
        for u in result["top_urls"][:10]:
            print(f"   • {u['url'][:70]}")

    if result.get("combos_sample"):
        print(f"\n📝 Sample combos:")
        for c in result["combos_sample"][:10]:
            print(f"   {c['email']}:{c['password']} [{c['domain']}] via {c['source']}")

    if result.get("stats", {}).get("by_source"):
        print(f"\n📊 By source:")
        for src, cnt in sorted(result["stats"]["by_source"].items(), key=lambda x: -x[1]):
            print(f"   {src}: {cnt}")
