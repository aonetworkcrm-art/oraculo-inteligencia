"""
╔══════════════════════════════════════════════════════════════╗
║  INTEL CONNECTORS — Threat Intelligence API Integrations     ║
║  Shodan · Hunter.io · HaveIBeenPwned · VirusTotal · Censys  ║
║  User-Agent Rotation · Rate Limiting · Graceful Degradation  ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import time
import json
import hashlib
import logging
import random
from datetime import datetime
from typing import Optional, List, Dict, Any

import requests

# Fallback to local keys when env vars are not set
from local_keys import (
    get_shodan_key, get_hunter_key, get_hibp_key,
    get_vt_key, get_censys_token,
)

logger = logging.getLogger("IntelConnectors")

# ─── User-Agent Pool (rotaciÃ³n anti-detecciÃ³n) ──────────────

USER_AGENTS = [
    # Chrome 125+ (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Firefox 127 (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    # Edge 125 (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Chrome (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Safari (macOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    # Chrome (Linux)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Mobile (Android Chrome)
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
]

def random_user_agent() -> str:
    """Return a random User-Agent string from the pool."""
    return random.choice(USER_AGENTS)


def rotate_session(session: Optional[requests.Session] = None) -> requests.Session:
    """Create or update a session with a random User-Agent."""
    if session is None:
        session = requests.Session()
    session.headers.update({
        "User-Agent": random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


# ─── Rate Limiter ────────────────────────────────────────────

class RateLimiter:
    """Simple token bucket rate limiter for API calls."""
    
    def __init__(self, requests_per_minute: int = 60):
        self.min_interval = 60.0 / max(requests_per_minute, 1)
        self.last_call = 0.0
    
    def wait(self):
        """Wait if needed to respect rate limit."""
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


# ─── Shodan Connector ────────────────────────────────────────

class ShodanConnector:
    """
    Shodan API connector — search for exposed services, hosts, and banners.
    
    API key: SHODAN_API_KEY env var
    Rate limit: 1 req/s (enforced by Shodan)
    Free tier: Limited query credits per month
    """
    
    BASE_URL = "https://api.shodan.io"
    
    def __init__(self):
        self.api_key = get_shodan_key()
        self.enabled = bool(self.api_key)
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        
        if self.enabled:
            logger.info("🔍 Shodan connector enabled")
        else:
            logger.info("🔍 Shodan connector disabled — set SHODAN_API_KEY")
    
    def search(self, query: str, limit: int = 20) -> dict:
        """
        Search Shodan for exposed services matching a query.
        
        Args:
            query: Shodan search query (e.g., "product:nginx country:US")
            limit: Maximum results to return
        
        Returns: {
            "success": bool,
            "total": int,
            "results": [ {ip, port, org, hostnames, services, ...} ],
            "error": str (if failed)
        }
        """
        if not self.enabled:
            return {"success": False, "error": "Shodan API key not configured", "total": 0, "results": []}
        
        self.rate_limiter.wait()
        
        try:
            resp = requests.get(
                f"{self.BASE_URL}/shodan/host/search",
                params={"key": self.api_key, "query": query, "limit": min(limit, 100)},
                timeout=15,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                matches = data.get("matches", [])
                results = []
                for m in matches[:limit]:
                    results.append({
                        "ip": m.get("ip_str", ""),
                        "port": m.get("port", 0),
                        "org": m.get("org", ""),
                        "hostnames": m.get("hostnames", []),
                        "country": m.get("location", {}).get("country_name", ""),
                        "city": m.get("location", {}).get("city", ""),
                        "services": [
                            {
                                "port": srv.get("port"),
                                "transport": srv.get("transport", ""),
                                "product": srv.get("product", ""),
                            }
                            for srv in m.get("data", [])
                        ] if isinstance(m.get("data"), list) else [],
                        "timestamp": m.get("timestamp", ""),
                        "source": "shodan",
                    })
                
                return {
                    "success": True,
                    "total": data.get("total", 0),
                    "results": results,
                    "query": query,
                }
            elif resp.status_code == 401:
                return {"success": False, "error": "Invalid Shodan API key", "total": 0, "results": []}
            elif resp.status_code == 403:
                return {"success": False, "error": "Shodan: out of query credits", "total": 0, "results": []}
            else:
                return {"success": False, "error": f"Shodan HTTP {resp.status_code}", "total": 0, "results": []}
        
        except requests.exceptions.Timeout:
            return {"success": False, "error": "Shodan request timed out", "total": 0, "results": []}
        except Exception as e:
            logger.error(f"Shodan search error: {e}")
            return {"success": False, "error": str(e), "total": 0, "results": []}
    
    def host(self, ip: str) -> dict:
        """Get detailed information about a specific host/IP."""
        if not self.enabled:
            return {"success": False, "error": "Shodan API key not configured"}
        
        self.rate_limiter.wait()
        
        try:
            resp = requests.get(
                f"{self.BASE_URL}/shodan/host/{ip}",
                params={"key": self.api_key},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "ip": ip,
                    "org": data.get("org", ""),
                    "asn": data.get("asn", ""),
                    "isp": data.get("isp", ""),
                    "country": data.get("country_name", ""),
                    "city": data.get("city", ""),
                    "ports": data.get("ports", []),
                    "hostnames": data.get("hostnames", []),
                    "os": data.get("os", ""),
                    "vulns": data.get("vulns", []),
                    "last_update": data.get("last_update", ""),
                    "source": "shodan",
                }
            else:
                return {"success": False, "error": f"Shodan HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── Hunter.io Connector ─────────────────────────────────────

class HunterConnector:
    """
    Hunter.io API connector — discover email addresses by domain.
    
    API key: HUNTER_API_KEY env var
    Free tier: 25 requests/month
    """
    
    BASE_URL = "https://api.hunter.io/v2"
    
    def __init__(self):
        self.api_key = get_hunter_key()
        self.enabled = bool(self.api_key)
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        
        if self.enabled:
            logger.info("📧 Hunter.io connector enabled")
        else:
            logger.info("📧 Hunter.io connector disabled — set HUNTER_API_KEY")
    
    def domain_search(self, domain: str, limit: int = 25) -> dict:
        """
        Find email addresses associated with a domain.
        
        Args:
            domain: Domain to search (e.g., "comcast.com")
            limit: Max results
        
        Returns: {
            "success": bool,
            "total": int,
            "emails": [ {value, type, confidence, sources, ...} ],
            "error": str (if failed)
        }
        """
        if not self.enabled:
            return {"success": False, "error": "Hunter API key not configured", "emails": [], "total": 0}
        
        self.rate_limiter.wait()
        
        try:
            resp = requests.get(
                f"{self.BASE_URL}/domain-search",
                params={"api_key": self.api_key, "domain": domain, "limit": min(limit, 100)},
                timeout=15,
            )
            
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                emails_raw = data.get("emails", [])
                emails = []
                for e in emails_raw[:limit]:
                    emails.append({
                        "value": e.get("value", ""),
                        "type": e.get("type", ""),  # personal, generic
                        "confidence": e.get("confidence", 0),
                        "first_name": e.get("first_name", ""),
                        "last_name": e.get("last_name", ""),
                        "position": e.get("position", ""),
                        "phone_number": e.get("phone_number", ""),
                        "sources": [
                            {"uri": s.get("uri", ""), "extracted_on": s.get("extracted_on", "")}
                            for s in (e.get("sources") or [])
                        ],
                    })
                
                return {
                    "success": True,
                    "domain": domain,
                    "total": len(emails),
                    "emails": emails,
                    "pattern": data.get("pattern", ""),
                    "organization": data.get("organization", ""),
                    "country": data.get("country", ""),
                }
            elif resp.status_code == 401:
                return {"success": False, "error": "Invalid Hunter API key", "emails": [], "total": 0}
            elif resp.status_code == 429:
                return {"success": False, "error": "Hunter: rate limit exceeded", "emails": [], "total": 0}
            else:
                return {"success": False, "error": f"Hunter HTTP {resp.status_code}", "emails": [], "total": 0}
        except Exception as e:
            logger.error(f"Hunter search error: {e}")
            return {"success": False, "error": str(e), "emails": [], "total": 0}
    
    def verify_email(self, email: str) -> dict:
        """Verify if an email address is deliverable."""
        if not self.enabled:
            return {"success": False, "error": "Hunter API key not configured"}
        
        self.rate_limiter.wait()
        
        try:
            resp = requests.get(
                f"{self.BASE_URL}/email-verifier",
                params={"api_key": self.api_key, "email": email},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                return {
                    "success": True,
                    "email": email,
                    "status": data.get("status", ""),  # valid, invalid, accept_all, unknown
                    "score": data.get("score", 0),
                    "smtp_check": data.get("smtp_check", False),
                    "disposable": data.get("disposable", False),
                    "webmail": data.get("webmail", False),
                }
            else:
                return {"success": False, "error": f"Hunter HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── HaveIBeenPwned Connector ────────────────────────────────

class HIBPConnector:
    """
    HaveIBeenPwned API v3 connector — check for data breaches by email or domain.
    
    API key: HIBP_API_KEY env var
    Requires: User-Agent header
    Free tier: Paid subscription required for breached account/domain endpoints
    """
    
    BASE_URL = "https://haveibeenpwned.com/api/v3"
    
    def __init__(self):
        self.api_key = get_hibp_key()
        self.enabled = bool(self.api_key)
        self.rate_limiter = RateLimiter(requests_per_minute=30)  # Conservative
        self.session = rotate_session()
        self.session.headers.update({
            "hibp-api-key": self.api_key,
            "User-Agent": "OracleIntel/1.0 (Threat Intelligence Research)",
        })
        
        if self.enabled:
            logger.info("🔒 HIBP connector enabled")
        else:
            logger.info("🔒 HIBP connector disabled — set HIBP_API_KEY")
    
    def check_email(self, email: str) -> dict:
        """
        Check if an email address appears in known data breaches.
        
        Args:
            email: Email address to check
        
        Returns: {
            "success": bool,
            "breaches": [ {name, domain, date, description, ...} ],
            "error": str
        }
        """
        if not self.enabled:
            return {"success": False, "error": "HIBP API key not configured", "breaches": [], "total": 0}
        
        self.rate_limiter.wait()
        
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/breachedaccount/{requests.utils.quote(email)}",
                params={"truncateResponse": "false"},
                timeout=15,
            )
            
            if resp.status_code == 200:
                breaches = resp.json()
                results = []
                for b in breaches:
                    results.append({
                        "name": b.get("Name", ""),
                        "domain": b.get("Domain", ""),
                        "date": b.get("BreachDate", ""),
                        "added_date": b.get("AddedDate", ""),
                        "pwn_count": b.get("PwnCount", 0),
                        "description": b.get("Description", "")[:500],
                        "data_classes": b.get("DataClasses", []),
                        "is_verified": b.get("IsVerified", False),
                        "is_fabricated": b.get("IsFabricated", False),
                        "is_retired": b.get("IsRetired", False),
                        "source": "hibp",
                    })
                
                return {
                    "success": True,
                    "email": email,
                    "total": len(results),
                    "breaches": results,
                }
            elif resp.status_code == 404:
                return {"success": True, "email": email, "total": 0, "breaches": [], "message": "No breaches found"}
            elif resp.status_code == 401:
                return {"success": False, "error": "Invalid HIBP API key", "breaches": [], "total": 0}
            elif resp.status_code == 429:
                return {"success": False, "error": "HIBP rate limit exceeded", "breaches": [], "total": 0}
            else:
                return {"success": False, "error": f"HIBP HTTP {resp.status_code}", "breaches": [], "total": 0}
        except Exception as e:
            logger.error(f"HIBP check_email error: {e}")
            return {"success": False, "error": str(e), "breaches": [], "total": 0}
    
    def check_domain(self, domain: str) -> dict:
        """
        Check all breached emails for a verified domain.
        Requires domain ownership verification in HIBP.
        """
        if not self.enabled:
            return {"success": False, "error": "HIBP API key not configured", "breaches": [], "total": 0}
        
        self.rate_limiter.wait()
        
        try:
            resp = self.session.get(
                f"{self.BASE_URL}/breacheddomain/{requests.utils.quote(domain)}",
                timeout=15,
            )
            if resp.status_code == 200:
                return {"success": True, "domain": domain, "breaches": resp.json()}
            elif resp.status_code == 404:
                return {"success": True, "domain": domain, "breaches": [], "message": "No domain breaches found"}
            else:
                return {"success": False, "error": f"HIBP HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_all_breaches(self) -> dict:
        """Get list of all known breaches in the HIBP database."""
        self.rate_limiter.wait()
        try:
            resp = self.session.get(f"{self.BASE_URL}/breaches", timeout=15)
            if resp.status_code == 200:
                return {"success": True, "total": len(resp.json()), "breaches": resp.json()}
            return {"success": False, "error": f"HIBP HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── VirusTotal Connector ────────────────────────────────────

class VirusTotalConnector:
    """
    VirusTotal API v3 connector — threat intelligence for domains, IPs, URLs, files.
    
    API key: VT_API_KEY env var
    Rate limit: 4 requests/minute (free)
    """
    
    BASE_URL = "https://www.virustotal.com/api/v3"
    
    def __init__(self):
        self.api_key = get_vt_key()
        self.enabled = bool(self.api_key)
        self.rate_limiter = RateLimiter(requests_per_minute=4)  # Free tier limit
        self.session = requests.Session()
        self.session.headers.update({
            "x-apikey": self.api_key,
            "User-Agent": random_user_agent(),
        })
        
        if self.enabled:
            logger.info("🦠 VirusTotal connector enabled")
        else:
            logger.info("🦠 VirusTotal connector disabled — set VT_API_KEY")
    
    def _get(self, path: str) -> Optional[dict]:
        """Make a GET request to VirusTotal API."""
        self.rate_limiter.wait()
        try:
            resp = self.session.get(f"{self.BASE_URL}{path}", timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"VT {resp.status_code}: {path}")
                return None
        except Exception as e:
            logger.error(f"VT request error: {e}")
            return None
    
    def analyze_domain(self, domain: str) -> dict:
        """
        Get threat intelligence report for a domain.
        
        Returns: {
            "success": bool,
            "domain": str,
            "malicious": int, "suspicious": int, "harmless": int,
            "categories": [str],
            "resolutions": [ {ip_address, date} ],
            "error": str
        }
        """
        if not self.enabled:
            return {"success": False, "error": "VT API key not configured"}
        
        result = self._get(f"/domains/{domain}")
        if result is None:
            return {"success": False, "error": "Domain not found in VT", "domain": domain}
        
        try:
            attrs = result.get("data", {}).get("attributes", {})
            stats = attrs.get("last_analysis_stats", {})
            categories = attrs.get("categories", {})
            resolutions_raw = attrs.get("resolutions", []) or []
            
            resolutions = []
            for r in resolutions_raw[:20]:
                if isinstance(r, dict):
                    r_attrs = r.get("attributes", r)
                    resolutions.append({
                        "ip": r_attrs.get("ip_address", ""),
                        "date": r_attrs.get("date", ""),
                    })
            
            return {
                "success": True,
                "domain": domain,
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "undetected": stats.get("undetected", 0),
                "reputation": attrs.get("reputation", 0),
                "categories": list(categories.values()),
                "resolutions": resolutions,
                "registrar": attrs.get("registrar", ""),
                "creation_date": attrs.get("creation_date", ""),
                "source": "virustotal",
            }
        except Exception as e:
            return {"success": False, "error": f"Parse error: {e}"}
    
    def analyze_ip(self, ip: str) -> dict:
        """Get threat intelligence report for an IP address."""
        if not self.enabled:
            return {"success": False, "error": "VT API key not configured"}
        
        result = self._get(f"/ip_addresses/{ip}")
        if result is None:
            return {"success": False, "error": "IP not found in VT", "ip": ip}
        
        try:
            attrs = result.get("data", {}).get("attributes", {})
            stats = attrs.get("last_analysis_stats", {})
            
            return {
                "success": True,
                "ip": ip,
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "reputation": attrs.get("reputation", 0),
                "country": attrs.get("country", ""),
                "asn": attrs.get("asn", ""),
                "as_owner": attrs.get("as_owner", ""),
                "source": "virustotal",
            }
        except Exception as e:
            return {"success": False, "error": f"Parse error: {e}"}


# ─── Censys Connector ────────────────────────────────────────

class CensysConnector:
    """
    Censys Platform API v3 connector — internet-wide asset discovery.
    
    API key: CENSYS_API_ID + CENSYS_API_SECRET or CENSYS_TOKEN env vars
    Free tier: Limited to host/certificate lookups, 1 concurrent action
    """
    
    BASE_URL = "https://api.platform.censys.io/v3/global"
    
    def __init__(self):
        self.token = get_censys_token()
        self.api_id = os.environ.get("CENSYS_API_ID", "")
        self.api_secret = os.environ.get("CENSYS_API_SECRET", "")
        
        # Support both auth methods
        if self.token:
            self.enabled = True
            self.session = requests.Session()
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "User-Agent": random_user_agent(),
                "Accept": "application/vnd.censys.api.v3.host.v1+json",
            })
        elif self.api_id and self.api_secret:
            self.enabled = True
            self.session = requests.Session()
            self.session.auth = (self.api_id, self.api_secret)
            self.session.headers.update({
                "User-Agent": random_user_agent(),
                "Accept": "application/vnd.censys.api.v3.host.v1+json",
            })
        else:
            self.enabled = False
            self.session = requests.Session()
        
        self.rate_limiter = RateLimiter(requests_per_minute=30)
        
        if self.enabled:
            logger.info("🌐 Censys connector enabled")
        else:
            logger.info("🌐 Censys connector disabled — set CENSYS_TOKEN or CENSYS_API_ID+SECRET")
    
    def search_hosts(self, query: str, limit: int = 20) -> dict:
        """
        Search Censys for hosts matching a query.
        
        Args:
            query: Censys search query (e.g., "services.service_name: HTTP")
            limit: Max results
        
        Returns: {
            "success": bool,
            "total": int,
            "results": [ {ip, services, location, ...} ],
            "error": str
        }
        """
        if not self.enabled:
            return {"success": False, "error": "Censys not configured", "total": 0, "results": []}
        
        self.rate_limiter.wait()
        
        try:
            resp = self.session.post(
                f"{self.BASE_URL}/hosts/search",
                json={"q": query, "per_page": min(limit, 100)},
                timeout=15,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                hits = data.get("result", {}).get("hits", [])
                results = []
                for h in hits[:limit]:
                    location = h.get("location", {}) or {}
                    services = h.get("services", []) or []
                    results.append({
                        "ip": h.get("ip", ""),
                        "services": [
                            {
                                "port": s.get("port"),
                                "service_name": s.get("service_name", s.get("transport_protocol", "")),
                                "transport": s.get("transport_protocol", ""),
                            }
                            for s in services[:5]
                        ],
                        "location": {
                            "country": location.get("country", ""),
                            "city": location.get("city", ""),
                            "coordinates": location.get("coordinates", {}),
                        },
                        "source": "censys",
                    })
                
                return {
                    "success": True,
                    "total": data.get("result", {}).get("total", 0),
                    "results": results,
                    "query": query,
                }
            else:
                return {"success": False, "error": f"Censys HTTP {resp.status_code}", "total": 0, "results": []}
        except Exception as e:
            logger.error(f"Censys search error: {e}")
            return {"success": False, "error": str(e), "total": 0, "results": []}
    
    def view_host(self, ip: str) -> dict:
        """Get detailed information about a specific host."""
        if not self.enabled:
            return {"success": False, "error": "Censys not configured"}
        
        self.rate_limiter.wait()
        
        try:
            resp = self.session.get(f"{self.BASE_URL}/hosts/{ip}", timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("result", {})
                return {
                    "success": True,
                    "ip": ip,
                    "services": data.get("services", []),
                    "location": data.get("location", {}),
                    "source": "censys",
                }
            return {"success": False, "error": f"Censys HTTP {resp.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ─── Multi-API Orchestrator ──────────────────────────────────

class IntelOrchestrator:
    """
    Orchestrates all intelligence connectors and returns unified results.
    Gracefully degrades if an API is unavailable or not configured.
    """
    
    def __init__(self):
        self.shodan = ShodanConnector()
        self.hunter = HunterConnector()
        self.hibp = HIBPConnector()
        self.virustotal = VirusTotalConnector()
        self.censys = CensysConnector()
        
        # Track which APIs are available
        self.available_apis = []
        if self.shodan.enabled: self.available_apis.append("shodan")
        if self.hunter.enabled: self.available_apis.append("hunter")
        if self.hibp.enabled: self.available_apis.append("hibp")
        if self.virustotal.enabled: self.available_apis.append("virustotal")
        if self.censys.enabled: self.available_apis.append("censys")
        
        logger.info(f"🤖 Intel Orchestrator ready — APIs available: {', '.join(self.available_apis) or 'none'}")
    
    def investigate_keyword(self, keyword: str) -> dict:
        """
        Run intelligence gathering across all available APIs for a keyword.
        Adapts the search based on what the keyword looks like (domain, IP, email, or generic).
        
        Args:
            keyword: Domain, IP, email, company name, or generic keyword
        
        Returns: {
            "keyword": str,
            "timestamp": str,
            "results": { ... per-source ... },
            "summary": { total_findings, critical_findings, ... }
        }
        """
        keyword = keyword.strip().lower()
        timestamp = datetime.now().isoformat()
        results = {}
        total_findings = 0
        critical_findings = 0
        
        # Detect keyword type — check IP and email FIRST before domain
        is_email = "@" in keyword
        is_ip = all(p.isdigit() for p in keyword.split(".")) and len(keyword.split(".")) == 4 \
                and all(0 <= int(p) <= 255 for p in keyword.split("."))
        is_domain = not is_email and not is_ip and "." in keyword \
                   and not keyword.startswith("http") and " " not in keyword
        is_generic = not is_domain and not is_ip and not is_email
        
        # ─── Shodan: search for exposed services ───
        if self.shodan.enabled:
            shodan_query = keyword if is_generic else f"org:\"{keyword}\""
            shodan_result = self.shodan.search(shodan_query, limit=15)
            results["shodan"] = shodan_result
            if shodan_result.get("success"):
                total_findings += len(shodan_result.get("results", []))
        
        # ─── Hunter.io: find emails by domain ───
        if self.hunter.enabled and (is_domain or is_generic):
            search_domain = keyword if is_domain else f"{keyword}.com"
            hunter_result = self.hunter.domain_search(search_domain, limit=20)
            results["hunter"] = hunter_result
            if hunter_result.get("success"):
                total_findings += hunter_result.get("total", 0)
        
        # ─── HIBP: check for breaches ───
        if self.hibp.enabled:
            if is_email:
                hibp_result = self.hibp.check_email(keyword)
            elif is_domain:
                hibp_result = self.hibp.check_domain(keyword)
            else:
                # For generic keywords, check the domain version
                hibp_result = self.hibp.check_domain(f"{keyword}.com")
            results["hibp"] = hibp_result
            if hibp_result.get("success"):
                total_findings += hibp_result.get("total", 0)
                critical_findings += hibp_result.get("total", 0)  # Breaches are always critical
        
        # ─── VirusTotal: analyze domain or IP ───
        if self.virustotal.enabled:
            if is_domain or is_generic:
                vt_domain = keyword if is_domain else f"{keyword}.com"
                vt_result = self.virustotal.analyze_domain(vt_domain)
                results["virustotal"] = vt_result
                if vt_result.get("success") and vt_result.get("malicious", 0) > 0:
                    critical_findings += vt_result["malicious"]
            
            if is_ip:
                vt_ip_result = self.virustotal.analyze_ip(keyword)
                results.setdefault("virustotal", {})
                results["virustotal_ip"] = vt_ip_result
                if vt_ip_result.get("success") and vt_ip_result.get("malicious", 0) > 0:
                    critical_findings += vt_ip_result["malicious"]
        
        # ─── Censys: search for exposed hosts ───
        if self.censys.enabled:
            censys_query = keyword if is_generic else f"services.service_name: {keyword}"
            censys_result = self.censys.search_hosts(censys_query, limit=15)
            results["censys"] = censys_result
            if censys_result.get("success"):
                total_findings += len(censys_result.get("results", []))
        
        return {
            "keyword": keyword,
            "timestamp": timestamp,
            "results": results,
            "summary": {
                "total_findings": total_findings,
                "critical_findings": critical_findings,
                "apis_queried": self.available_apis.copy(),
                "apis_configured": len(self.available_apis),
                "detected_type": "domain" if is_domain else ("ip" if is_ip else ("email" if is_email else "keyword")),
            }
        }


# ─── CLI Test ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    keyword = sys.argv[1] if len(sys.argv) > 1 else "comcast"
    
    orchestrator = IntelOrchestrator()
    print(f"\n🔍 Investigating: {keyword}")
    print(f"   APIs available: {orchestrator.available_apis}")
    print(f"   Detected type: {orchestrator.investigate_keyword(keyword)['summary']['detected_type']}")
    print(f"\n📊 Summary: {json.dumps(orchestrator.investigate_keyword(keyword)['summary'], indent=2)}")
