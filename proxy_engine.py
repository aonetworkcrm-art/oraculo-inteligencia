"""
╔══════════════════════════════════════════════════════════════╗
║  PROXY ENGINE — Unified Proxy Management System v2.0        ║
║  Basado en: VZ ProxyManager + Oracle ComboLeecher            ║
║                                                              ║
║  Características:                                             ║
║  - Pool de proxies con testeo automático                      ║
║  - Scraping de 20+ fuentes gratuitas                          ║
║  - Modo proxyless (conexión directa)                          ║
║  - VPN detection                                              ║
║  - Rotación round-robin + dead detection                      ║
║  - WebSocket para actualizaciones en tiempo real              ║
║  - ProxyBroker2 (50+ fuentes, opcional)                       ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import random
import logging
import threading
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("ProxyEngine")


# ═══════════════════════════════════════════════════════════════
#  VPN / REGION DETECTION
# ═══════════════════════════════════════════════════════════════

def detect_vpn() -> dict:
    """
    Detect if the current connection is behind a VPN.
    Uses: ip-api.com, ifconfig.me, or ipify.org
    Returns: {"vpn": bool, "ip": str, "country": str, "isp": str, "proxy": bool}
    """
    result = {"vpn": False, "ip": "", "country": "", "isp": "", "proxy": False}
    services = [
        "https://ipapi.co/json/",
        "https://ip-api.com/json/",
        "https://api.ipify.org?format=json",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    for url in services:
        try:
            resp = requests.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                ip = data.get("ip") or data.get("query", "")
                if ip:
                    result["ip"] = ip
                    result["country"] = data.get("country", data.get("countryCode", ""))
                    result["isp"] = data.get("org", data.get("isp", ""))
                    result["vpn"] = data.get("proxy", data.get("vpn", False))
                    result["hosting"] = data.get("hosting", False)
                    break
        except Exception:
            continue

    return result


# ═══════════════════════════════════════════════════════════════
#  PROXY POOL
# ═══════════════════════════════════════════════════════════════

class ProxyPool:
    """
    Unified proxy pool with:
    - Round-robin rotation
    - Dead proxy detection
    - Auto-testing (HTTP/HTTPS/SOCKS)
    - Stats tracking
    - WebSocket event emitter
    """

    def __init__(self, ws_emit: Optional[Callable] = None):
        self.proxies: List[dict] = []  # {server, username, password, alive, latency, test_time, source}
        self._index = 0
        self._lock = threading.Lock()
        self._test_progress = {"total": 0, "tested": 0, "alive": 0, "dead": 0}
        self._abort_flag = False
        self.ws_emit = ws_emit  # Function to emit WebSocket events
        self._load_from_env()

    def _load_from_env(self):
        """Load proxies from COMBO_PROXIES env var."""
        proxy_list = os.environ.get("COMBO_PROXIES", "")
        if proxy_list:
            for p in proxy_list.split(","):
                p = p.strip()
                if p:
                    self.add(p)

    # ─── Pool Management ───

    def add(self, proxy_str: str, source: str = "manual") -> bool:
        """Add a single proxy from URL string. Returns True if added."""
        proxy = self._parse(proxy_str)
        if not proxy:
            return False
        proxy["alive"] = None       # None = untested
        proxy["test_time"] = None
        proxy["latency"] = None
        proxy["source"] = source
        with self._lock:
            # Avoid duplicates
            for existing in self.proxies:
                if existing.get("server") == proxy.get("server"):
                    return False
            self.proxies.append(proxy)
        return True

    def add_list(self, text: str, source: str = "list") -> int:
        """Add multiple proxies from text (one per line). Returns count."""
        count = 0
        for line in text.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                if self.add(line, source=source):
                    count += 1
        return count

    def remove(self, server: str) -> bool:
        """Remove a proxy by server address."""
        with self._lock:
            self.proxies = [p for p in self.proxies if p.get("server") != server]
        return True

    def clear(self):
        """Clear all proxies."""
        with self._lock:
            self.proxies = []
            self._index = 0
            self._test_progress = {"total": 0, "tested": 0, "alive": 0, "dead": 0}

    def remove_dead(self):
        """Remove all proxies that failed testing."""
        with self._lock:
            self.proxies = [p for p in self.proxies if p.get("alive") is not False]

    # ─── Rotation ───

    def get_next(self) -> Optional[dict]:
        """Get next alive proxy (round-robin). Returns None if none alive."""
        with self._lock:
            alive = [p for p in self.proxies if p.get("alive") is True]
            if not alive:
                return None
            if self._index >= len(alive):
                self._index = 0
            proxy = alive[self._index]
            self._index += 1
            return dict(proxy)  # Return copy

    def get_random(self) -> Optional[dict]:
        """Get a random alive proxy. For requests library."""
        with self._lock:
            alive = [p for p in self.proxies if p.get("alive") is True]
            if not alive:
                return None
            proxy_str = random.choice(alive)["server"]
        return {"http": proxy_str, "https": proxy_str}

    def mark_alive(self, server: str, latency: float = 0):
        """Mark a proxy as alive."""
        with self._lock:
            for p in self.proxies:
                if p["server"] == server:
                    p["alive"] = True
                    p["latency"] = latency
                    p["test_time"] = datetime.now().isoformat()
                    return True
        return False

    def mark_dead(self, server: str):
        """Mark a proxy as dead."""
        with self._lock:
            for p in self.proxies:
                if p["server"] == server:
                    p["alive"] = False
                    p["test_time"] = datetime.now().isoformat()
                    return True
        return False

    # ─── Stats ───

    def stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            total = len(self.proxies)
            alive = sum(1 for p in self.proxies if p.get("alive") is True)
            dead = sum(1 for p in self.proxies if p.get("alive") is False)
            untested = sum(1 for p in self.proxies if p.get("alive") is None)
            by_source = {}
            for p in self.proxies:
                src = p.get("source", "unknown")
                by_source[src] = by_source.get(src, 0) + 1
            return {
                "total": total,
                "alive": alive,
                "dead": dead,
                "untested": untested,
                "by_source": by_source,
                "proxyless_available": True,
            }

    def get_alive(self) -> List[dict]:
        """Get list of alive proxies."""
        with self._lock:
            return [dict(p) for p in self.proxies if p.get("alive") is True]

    # ─── Testing ───

    TEST_URLS = [
        "https://httpbin.org/ip",
        "https://api.ipify.org?format=json",
    ]

    def test_all(self, progress_callback: Optional[Callable] = None,
                 timeout: int = 10, test_url: str = None):
        """
        Test all untested proxies.
        Uses requests library (faster than Playwright for simple HTTP test).
        """
        with self._lock:
            pending = [p for p in self.proxies if p.get("alive") is None]
            self._test_progress = {
                "total": len(pending),
                "tested": 0,
                "alive": 0,
                "dead": 0,
            }

        if not pending:
            if progress_callback:
                progress_callback({"total": 0, "tested": 0, "alive": 0, "dead": 0,
                                   "message": "No proxies to test"})
            self._emit_ws("proxy_test_complete", self.stats())
            return

        if progress_callback:
            progress_callback({**self._test_progress,
                               "message": f"Testing {len(pending)} proxies..."})

        url = test_url or self.TEST_URLS[0]
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

        for i, proxy in enumerate(pending):
            if self._abort_flag:
                break

            result = self._test_one(proxy, url, headers, timeout)

            with self._lock:
                for p in self.proxies:
                    if p["server"] == proxy["server"]:
                        p["alive"] = result["alive"]
                        p["latency"] = result.get("latency")
                        p["test_time"] = datetime.now().isoformat()
                        break

                self._test_progress["tested"] += 1
                if result["alive"]:
                    self._test_progress["alive"] += 1
                else:
                    self._test_progress["dead"] += 1

            msg = (f"[{i+1}/{len(pending)}] {proxy['server']} → "
                   f"{'✅ ALIVE' if result['alive'] else '💀 DEAD'}"
                   f" ({result.get('latency', 0):.0f}ms)" if result.get('latency') else
                   f"{'✅ ALIVE' if result['alive'] else '💀 DEAD'}")
            if progress_callback:
                progress_callback({**self._test_progress, "message": msg})

            self._emit_ws("proxy_tested", {
                "server": proxy["server"],
                "alive": result["alive"],
                "latency": result.get("latency", 0),
                "progress": self._test_progress,
            })

        if progress_callback:
            stats = self.stats()
            progress_callback({**self._test_progress,
                               "message": f"Complete: {stats['alive']} alive, {stats['dead']} dead"})
        self._emit_ws("proxy_test_complete", self.stats())

    def _test_one(self, proxy: dict, url: str, headers: dict, timeout: int) -> dict:
        """Test a single proxy."""
        result = {"alive": False, "latency": 0}
        try:
            proxy_dict = {"http": proxy["server"], "https": proxy["server"]}
            start = time.time()
            resp = requests.get(url, headers=headers, proxies=proxy_dict,
                                timeout=timeout)
            latency = (time.time() - start) * 1000
            result["latency"] = latency

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if "origin" in data:
                        result["alive"] = True
                        result["ip"] = data["origin"]
                    else:
                        result["alive"] = True
                except Exception:
                    result["alive"] = True  # Response OK but not JSON
            else:
                result["alive"] = False
                result["error"] = f"HTTP {resp.status_code}"
        except requests.exceptions.ConnectTimeout:
            result["alive"] = False
            result["error"] = "timeout"
        except requests.exceptions.ProxyError as e:
            result["alive"] = False
            result["error"] = str(e)[:60]
        except Exception as e:
            result["alive"] = False
            result["error"] = str(e)[:60]
        return result

    def abort(self):
        """Abort current test/scrape operation."""
        self._abort_flag = True

    # ─── WebSocket Emit ───

    def _emit_ws(self, event: str, data: dict):
        """Emit WebSocket event if emitter is configured."""
        if self.ws_emit:
            try:
                self.ws_emit(event, data)
            except Exception:
                pass

    # ─── Persistence ───

    def save_alive(self, filepath: str = None) -> int:
        """Save alive proxies to a text file."""
        if filepath is None:
            filepath = os.path.join(os.path.dirname(__file__), "proxies_vivos.txt")
        alive = self.get_alive()
        if not alive:
            return 0
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Alive proxies - {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(f"# Total: {len(alive)}\n\n")
            for p in alive:
                server = p["server"]
                user = p.get("username", "")
                pwd = p.get("password", "")
                if user and pwd:
                    scheme, host = server.split("://", 1) if "://" in server else ("http", server)
                    f.write(f"{scheme}://{user}:{pwd}@{host}\n")
                else:
                    f.write(f"{server}\n")
        return len(alive)

    def load_from_file(self, filepath: str) -> int:
        """Load proxies from a text file."""
        if not os.path.exists(filepath):
            return 0
        with open(filepath, "r", encoding="utf-8") as f:
            return self.add_list(f.read(), source="file")

    # ─── Parsing ───

    @staticmethod
    def _parse(proxy_str: str) -> Optional[dict]:
        """Parse proxy string into dict {server, username, password}."""
        proxy_str = proxy_str.strip()
        if not proxy_str or proxy_str.startswith("#"):
            return None

        # If has protocol: http://user:pass@host:port
        if "://" in proxy_str:
            try:
                parsed = urlparse(proxy_str)
                server = f"{parsed.scheme}://{parsed.hostname}"
                if parsed.port:
                    server += f":{parsed.port}"
                return {
                    "server": server,
                    "username": parsed.username or "",
                    "password": parsed.password or "",
                }
            except Exception:
                return None
        else:
            # host:port or user:pass@host:port
            if "@" in proxy_str:
                auth, hostpart = proxy_str.split("@", 1)
                user, pwd = auth.split(":", 1) if ":" in auth else (auth, "")
                return {"server": f"http://{hostpart}", "username": user, "password": pwd}
            else:
                return {"server": f"http://{proxy_str}", "username": "", "password": ""}


# ═══════════════════════════════════════════════════════════════
#  PROXY SCRAPER — Auto-collect from free sources
# ═══════════════════════════════════════════════════════════════

class ProxyScraper:
    """
    Scrapes free proxy lists from 20+ sources.
    Basado en: VZ ProxyManager FUENTES_PROXIES + nuevas fuentes.
    """

    SOURCES = [
        # ─── HTTP/HTTPS ───
        {"url": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/http_all.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt", "type": "txt"},
        {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt", "type": "txt"},
        # ─── SOCKS5 ───
        {"url": "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/VPSLabCloud/VPSLab-Free-Proxy-List/main/socks5.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks5.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/socks5.txt", "type": "txt"},
        {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "type": "txt"},
        # ─── SOCKS4 ───
        {"url": "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Socks4.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/socks4.txt", "type": "txt"},
        {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt", "type": "txt"},
        # ─── Mixed ───
        {"url": "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies.txt", "type": "txt"},
        {"url": "https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list.txt", "type": "txt"},
        # ─── Free Proxy List (HTML tables) ───
        # Formato: <table> con columnas IP, Port, Code, Country, ...
        # Cada entrada incluye el protocol por defecto para ese origen
        {"url": "https://free-proxy-list.net/",          "type": "html_table", "protocol": "http"},
        {"url": "https://free-proxy-list.net/uk-proxy.html", "type": "html_table", "protocol": "http"},
        {"url": "https://sslproxies.org/",               "type": "html_table", "protocol": "https"},
        {"url": "https://us-proxy.org/",                 "type": "html_table", "protocol": "http"},
        {"url": "https://socks-proxy.net/",              "type": "html_table", "protocol": "socks5"},
        {"url": "https://proxy-nl.com/",                 "type": "html_table", "protocol": "http"},
        # ─── API sources (JSON) ───
        {"url": "https://proxylist.geonode.com/api/proxy-list?limit=200&page=1&sort_by=lastChecked&sort_type=desc&protocols=http%2Chttps", "type": "geonode"},
        {"url": "https://api.openproxy.space/list?skip=0&ts=1", "type": "openproxy"},
        {"url": "https://www.proxy-list.download/api/v1/get?type=http", "type": "proxy_dl"},
        {"url": "https://www.proxy-list.download/api/v1/get?type=socks5", "type": "proxy_dl"},
        {"url": "https://proxydb.net/?protocol=http&protocol=https&protocol=socks4&protocol=socks5", "type": "html_table", "protocol": "http"},
        {"url": "https://www.proxynova.com/proxy-server-list/", "type": "html_table", "protocol": "http"},
    ]

    def __init__(self, pool: ProxyPool):
        self.pool = pool
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        self._abort = False

    def scrape_all(self, progress_callback: Optional[Callable] = None) -> dict:
        """Scrape all sources. Returns {total, by_source: {name: count}}."""
        self._abort = False
        result = {"total": 0, "by_source": {}, "errors": []}
        total = len(self.SOURCES)

        for i, source in enumerate(self.SOURCES):
            if self._abort:
                break

            url = source["url"]
            # Extract domain as name, handle URLs ending in /
            name = source.get("name") or url.rstrip("/").split("/")[-1] or url.split("//")[-1].split("/")[0]
            source_type = source["type"]

            if progress_callback:
                progress_callback({"message": f"[{i+1}/{total}] {name}"})

            try:
                resp = self.session.get(url, timeout=20)
                if resp.status_code != 200:
                    continue

                count = 0
                # Get protocol for html_table sources (default http)
                protocol = source.get("protocol", "http") if source_type == "html_table" else "http"

                if source_type == "txt":
                    count = self._parse_txt(resp.text, source=name)
                elif source_type == "geonode":
                    count = self._parse_geonode(resp.text, source=name)
                elif source_type == "openproxy":
                    count = self._parse_openproxy(resp.text, source=name)
                elif source_type == "proxy_dl":
                    count = self._parse_proxy_dl(resp.text, source=name)
                elif source_type == "html_table":
                    count = self._parse_html_table(resp.text, source=name, default_protocol=protocol)

                if count > 0:
                    result["total"] += count
                    result["by_source"][name] = count
                    if progress_callback:
                        progress_callback({"message": f"  → {count} proxies added"})

            except Exception as e:
                result["errors"].append(f"{name}: {e}")
                if progress_callback:
                    progress_callback({"message": f"  → Error: {str(e)[:50]}"})

        # Try ProxyScrape API
        if not self._abort:
            ps_count = self._scrape_proxyscrape(protocols=["http", "socks4"])
            if ps_count > 0:
                result["total"] += ps_count
                result["by_source"]["proxyscrape"] = ps_count

        # Try ProxyBroker2 (50+ sources, requires pip install)
        if not self._abort:
            pb_count = self._scrape_proxybroker(limit=500, progress_callback=progress_callback)
            if pb_count > 0:
                result["total"] += pb_count
                result["by_source"]["proxybroker2"] = pb_count

        return result

    def _parse_txt(self, text: str, source: str = "github") -> int:
        """Parse plain text IP:PORT format."""
        count = 0
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                if line.startswith("http://") or line.startswith("socks"):
                    proxy_str = line
                else:
                    proxy_str = f"http://{line}"
                if self.pool.add(proxy_str, source=source):
                    count += 1
        return count

    def _parse_geonode(self, text: str, source: str = "geonode") -> int:
        """Parse Geonode API JSON response."""
        count = 0
        try:
            data = json.loads(text)
            proxies = data.get("data", [])
            for p in proxies:
                ip = p.get("ip", "")
                port = p.get("port", "")
                protocols = p.get("protocols", ["http"])
                if ip and port:
                    proto = protocols[0] if protocols else "http"
                    proxy_str = f"{proto}://{ip}:{port}"
                    if self.pool.add(proxy_str, source=source):
                        count += 1
        except Exception:
            pass
        return count

    def _parse_openproxy(self, text: str, source: str = "openproxy") -> int:
        """Parse OpenProxy.space JSON response."""
        count = 0
        try:
            data = json.loads(text)
            for item in data:
                ip = item.get("ip", "")
                port = item.get("port", "")
                if ip and port:
                    proxy_str = f"http://{ip}:{port}"
                    if self.pool.add(proxy_str, source=source):
                        count += 1
        except Exception:
            pass
        return count

    def _parse_proxy_dl(self, text: str, source: str = "proxy-dl") -> int:
        """Parse Proxy-List.download API response."""
        count = 0
        for line in text.strip().split("\n"):
            line = line.strip()
            if ":" in line and not line.startswith("["):
                proxy_str = f"http://{line}"
                if self.pool.add(proxy_str, source=source):
                    count += 1
        return count

    def _parse_html_table(self, html: str, source: str = "free-proxy-list",
                          default_protocol: str = "http") -> int:
        """
        Parse HTML table format from free-proxy-list.net and similar sites.
        
        Formato típico:
        <table class="table table-striped table-bordered">
          <tr><td>IP</td><td>PORT</td><td>Code</td><td>Country</td>...
        
        Args:
            html: HTML content to parse
            source: Source name for tracking
            default_protocol: Protocol prefix (http, https, socks5, socks4)
        """
        count = 0
        
        # Patrón para validar IP
        IP_RE = re.compile(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$')
        
        def _is_valid_ip(ip: str) -> bool:
            m = IP_RE.match(ip)
            if not m:
                return False
            return all(0 <= int(g) <= 255 for g in m.groups())
        
        def _extract_text(cell) -> str:
            """Extrae texto plano de una celda, saltando enlaces y abbr."""
            # proxynova.com usa <abbr title="..."> dentro del td
            abbr = cell.find("abbr")
            if abbr and abbr.get("title"):
                return abbr["title"].strip()
            # Enlaces con href
            link = cell.find("a")
            if link and link.get_text(strip=True):
                return link.get_text(strip=True)
            return cell.get_text(strip=True)

        try:
            soup = BeautifulSoup(html, "html.parser")

            # Intentar: tablas con clase específica primero
            tables = soup.find_all("table", class_=re.compile(
                r"table|proxy|list|data", re.IGNORECASE
            ))
            if not tables:
                tables = soup.find_all("table")

            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) < 2:
                        continue

                    ip = _extract_text(cells[0])
                    port = _extract_text(cells[1])

                    # Limpiar: quitar espacios, saltos de línea
                    ip = ip.replace("\n", "").replace(" ", "").strip()
                    port = port.replace("\n", "").replace(" ", "").strip()

                    # Validar IP completa (incluyendo rango 0-255)
                    if ip and port and _is_valid_ip(ip):
                        # Validar puerto (1-65535)
                        try:
                            port_num = int(port)
                            if port_num < 1 or port_num > 65535:
                                continue
                        except ValueError:
                            continue

                        proxy_str = f"{default_protocol}://{ip}:{port}"
                        if self.pool.add(proxy_str, source=source):
                            count += 1

        except Exception as e:
            logger.debug(f"HTML table parse error ({source}): {e}")

        return count

    def _scrape_proxyscrape(self, protocols: list = None, timeout_ms: int = 10000) -> int:
        """Scrape from ProxyScrape API."""
        if protocols is None:
            protocols = ["http", "socks4"]
        total = 0
        for protocol in protocols:
            if self._abort:
                break
            url = (f"https://api.proxyscrape.com/v2/?request=displayproxies"
                   f"&protocol={protocol}&timeout={timeout_ms}"
                   f"&country=all&ssl=all&anonymity=all")
            try:
                resp = self.session.get(url, timeout=30)
                if resp.status_code == 200:
                    for line in resp.text.strip().split("\n"):
                        line = line.strip()
                        if ":" in line:
                            if self.pool.add(f"http://{line}", source="proxyscrape"):
                                total += 1
            except Exception:
                pass
        return total

    def _scrape_proxybroker(self, limit: int = 500,
                            progress_callback: Optional[Callable] = None) -> int:
        """Use ProxyBroker2 to scrape 50+ sources (optional dependency)."""
        try:
            from proxybroker2 import Broker
        except ImportError:
            if progress_callback:
                progress_callback({"message": "[PROXYBROKER] pip install proxybroker2 for 50+ sources"})
            return 0

        total = 0
        if progress_callback:
            progress_callback({"message": f"[PROXYBROKER] Scraping 50+ sources (limit={limit})..."})

        async def _find():
            nonlocal total
            queue = asyncio.Queue()
            broker = Broker(queue)
            task = asyncio.create_task(broker.find(types=['HTTP', 'HTTPS', 'SOCKS5'], limit=limit))

            received = 0
            while True:
                if self._abort:
                    task.cancel()
                    break
                try:
                    proxy = await asyncio.wait_for(queue.get(), timeout=3)
                except asyncio.TimeoutError:
                    if task.done():
                        break
                    continue
                if proxy is None:
                    break
                raw_type = getattr(proxy, 'type', 'HTTP')
                proto = raw_type.name.lower() if hasattr(raw_type, 'name') else str(raw_type).lower()
                host = getattr(proxy, 'host', '')
                port = getattr(proxy, 'port', '')
                if host and port:
                    proxy_str = f"{proto}://{host}:{port}"
                    if self.pool.add(proxy_str, source="proxybroker2"):
                        total += 1
                        received += 1
                    if received % 50 == 0 and progress_callback:
                        progress_callback({"message": f"[PROXYBROKER] {received} proxies..."})

            try:
                await task
            except Exception:
                pass

        try:
            asyncio.run(_find())
        except Exception as e:
            if progress_callback:
                progress_callback({"message": f"[PROXYBROKER] Error: {str(e)[:60]}"})

        if progress_callback:
            progress_callback({"message": f"[PROXYBROKER] Done: {total} proxies"})
        return total

    def abort(self):
        """Abort scraping."""
        self._abort = True


# ═══════════════════════════════════════════════════════════════
#  UNIFIED PROXY ENGINE
# ═══════════════════════════════════════════════════════════════

class ProxyEngine:
    """
    Unified proxy engine combining all proxy features.
    Designed to replace the basic ProxyManager in combo_leecher_engine.py.

    Features:
    - Proxy pool with round-robin rotation
    - Auto-scraping from 20+ sources
    - Auto-testing (HTTP/HTTPS/SOCKS)
    - Proxyless mode (direct connection)
    - VPN detection
    - Dead proxy detection
    - WebSocket events for real-time updates
    - Stats tracking
    """

    def __init__(self, ws_emit: Optional[Callable] = None):
        self.pool = ProxyPool(ws_emit=ws_emit)
        self.scraper = ProxyScraper(self.pool)
        self.ws_emit = ws_emit
        self._mode = "auto"  # "auto", "proxyless", "proxy"
        self._vpn_info = {}

    # ─── Mode ───

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if value in ("auto", "proxyless", "proxy"):
            self._mode = value

    def set_proxyless(self):
        """Enable proxyless mode (direct connection)."""
        self._mode = "proxyless"
        logger.info("🌐 Proxyless mode enabled — using direct connection")
        self._emit_ws("proxy_mode", {"mode": "proxyless"})

    def set_proxy_mode(self):
        """Enable proxy mode."""
        self._mode = "proxy"
        logger.info("🔌 Proxy mode enabled")
        self._emit_ws("proxy_mode", {"mode": "proxy"})

    def set_auto_mode(self):
        """Auto mode: use proxies if available, fall back to direct."""
        self._mode = "auto"
        logger.info("🔄 Auto mode enabled")
        self._emit_ws("proxy_mode", {"mode": "auto"})

    # ─── Connection ───

    def get_proxy_for_request(self) -> Optional[dict]:
        """
        Get proxy dict for requests library based on current mode.
        Returns None if proxyless or no proxies available.
        """
        if self._mode == "proxyless":
            return None

        if self._mode == "auto":
            proxy = self.pool.get_random()
            if proxy:
                return proxy
            # Fallback to direct
            return None

        # Proxy mode — require a proxy
        return self.pool.get_random()

    # ─── VPN Detection ───

    def detect_vpn(self) -> dict:
        """Detect if behind VPN and return connection info."""
        self._vpn_info = detect_vpn()
        logger.info(f"🌍 Connection: {self._vpn_info.get('ip')} "
                    f"[{self._vpn_info.get('country')}] "
                    f"{'🔒 VPN' if self._vpn_info.get('vpn') else '🔓 Direct'}")
        self._emit_ws("vpn_detected", self._vpn_info)
        return self._vpn_info

    # ─── Operations ───

    def scrape_proxies(self, progress_callback: Optional[Callable] = None) -> dict:
        """Scrape proxies from all free sources."""
        logger.info("🕸️  Scraping proxies from 20+ free sources...")
        self._emit_ws("proxy_scrape_start", {})
        result = self.scraper.scrape_all(progress_callback=progress_callback)
        logger.info(f"✅ Scraped {result['total']} total proxies from {len(result['by_source'])} sources")
        self._emit_ws("proxy_scrape_complete", {
            **result,
            "pool_stats": self.pool.stats(),
        })
        return result

    def test_proxies(self, progress_callback: Optional[Callable] = None) -> dict:
        """Test all untested proxies."""
        logger.info("🧪 Testing proxies...")
        self._emit_ws("proxy_test_start", {})
        self.pool.test_all(progress_callback=progress_callback)
        stats = self.pool.stats()
        logger.info(f"✅ Test complete: {stats['alive']} alive / {stats['dead']} dead / {stats['untested']} untested")
        return stats

    def get_stats(self) -> dict:
        """Get full engine stats."""
        pool_stats = self.pool.stats()
        return {
            "pool": pool_stats,
            "mode": self._mode,
            "vpn": self._vpn_info,
            "scrape_sources": len(self.scraper.SOURCES),
        }

    # ─── WebSocket ───

    def set_ws_emit(self, ws_emit: Callable):
        """Set WebSocket emitter function."""
        self.pool.ws_emit = ws_emit
        self.ws_emit = ws_emit

    def _emit_ws(self, event: str, data: dict):
        """Emit WebSocket event."""
        if self.ws_emit:
            try:
                self.ws_emit(event, data)
            except Exception:
                pass

    # ─── Abort ───

    def abort(self):
        """Abort all operations."""
        self.scraper.abort()
        self.pool.abort()
