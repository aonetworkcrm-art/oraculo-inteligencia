"""
╔══════════════════════════════════════════════════════════════╗
║  ORÁCULO DE INTELIGENCIA — Threat Intelligence Oracle v1.0  ║
║  Motor de OSINT, Dorking Automatizado & Indexación           ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, quote_plus

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OracleEngine")

# ─── Data Models ──────────────────────────────────────────────

@dataclass
class IntelligenceRecord:
    """A single intelligence finding (credential, leak, config, etc.)"""
    id: str = ""
    keyword: str = ""
    source_url: str = ""
    source_type: str = ""  # pastebin, github, shodan, public_directory, etc.
    record_type: str = ""  # email:pass, user:pass, api_key, config, log
    content_preview: str = ""
    discovered_at: str = ""
    discovered_date: str = ""
    severity: str = "info"  # critical, high, medium, low, info
    domain: str = ""
    email: str = ""
    username: str = ""
    password: str = ""
    hash_type: str = ""
    hash_value: str = ""
    ip_address: str = ""
    port: str = ""
    extra_data: dict = field(default_factory=dict)
    
    def to_dict(self):
        return asdict(self)


@dataclass
class DorkResult:
    """Result from an automated dorking operation"""
    url: str = ""
    title: str = ""
    snippet: str = ""
    source: str = ""
    discovered_at: str = ""
    discovered_date: str = ""


@dataclass
class IntelligenceReport:
    """Aggregated intelligence report for a keyword search"""
    keyword: str = ""
    timestamp: str = ""
    total_records: int = 0
    records: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# ─── Oracle Engine ────────────────────────────────────────────

class OracleEngine:
    """
    Core intelligence engine that performs:
    - Automated dorking across search engines
    - Paste site scraping
    - Public repository discovery
    - Pattern matching & extraction (email:pass, api keys, etc.)
    - Data indexing & organization
    """
    
    def __init__(self, cache_dir: str = ".oracle_cache"):
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        })
        
        # Pattern definitions for data extraction
        self.patterns = {
            "email_password": re.compile(
                r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[:;|]\s*(\S+)', 
                re.IGNORECASE
            ),
            "username_password": re.compile(
                r'(?:user(?:name)?|login|Usuario)\s*[:;|=\s]\s*(\S+)\s*\n?\s*(?:pass|password|contraseña|clave|pw|pwd)\s*[:;|=\s]\s*(\S+)',
                re.IGNORECASE
            ),
            "api_key": re.compile(
                r'(?:api[_-]?key|apikey|api[_-]?secret|api[_-]?token)\s*[:;|=\s"\']\s*([A-Za-z0-9_\-]{16,})',
                re.IGNORECASE
            ),
            "ip_port": re.compile(
                r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\s*[:;|]\s*(\d{2,5})'
            ),
            "hash_value": re.compile(
                r'\b([a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})\b',
                re.IGNORECASE
            ),
            "ssn": re.compile(
                r'\b(\d{3}[-]\d{2}[-]\d{4})\b'
            ),
            "credit_card": re.compile(
                r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
            ),
            "jwt_token": re.compile(
                r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}'
            ),
        }
        
        # Dork templates organized by category
        self.dork_templates = {
            "logs": [
                'inurl:"/logs/" intitle:"index of" {keyword}',
                'filetype:log "{keyword}"',
                'inurl:"/var/log/" "{keyword}"',
                'inurl:"/log/" "{keyword}" password',
            ],
            "credentials": [
                'intext:"{keyword}" intext:"password" filetype:txt',
                'intext:"{keyword}" intext:"email" intext:"password"',
                'intext:"{keyword}" intext:"@gmail.com" intext:":pass"',
                'intitle:"index of" "{keyword}" "passwd"',
            ],
            "databases": [
                'inurl:"/sql/" intitle:"index of" {keyword}',
                'intext:"{keyword}" filetype:sql "INSERT INTO"',
                'intext:"{keyword}" filetype:sql "VALUES" "@"',
                'inurl:"/backup/" "{keyword}"',
            ],
            "config_files": [
                'intext:"{keyword}" filetype:env "DB_PASSWORD"',
                'intext:"{keyword}" filetype:config "password"',
                'intext:"{keyword}" filetype:ini "password"',
                'intext:"{keyword}" filetype:xml "password"',
            ],
            "paste_sites": [
                'site:pastebin.com "{keyword}"',
                'site:paste.ee "{keyword}"',
                'site:pastebin.ee "{keyword}"',
                'site:rentry.co "{keyword}"',
                'site:ghostbin.co "{keyword}"',
            ],
            "exposed_directories": [
                'intitle:"index of" "{keyword}" "backup"',
                'intitle:"index of" "{keyword}" "admin"',
                'intitle:"index of" "{keyword}" "private"',
                'intitle:"index of" "{keyword}" "confidential"',
            ],
            "code_repos": [
                'site:github.com "{keyword}" password',
                'site:gitlab.com "{keyword}" password',
                'site:bitbucket.org "{keyword}" password',
                'site:github.com "{keyword}" "api_key"',
            ],
            "exploit_db": [
                'site:exploit-db.com "{keyword}"',
                'site:packetstormsecurity.com "{keyword}"',
                'site:cxsecurity.com "{keyword}"',
            ],
        }
        
        # Known paste site URLs for direct scraping
        self.paste_urls = [
            "https://pastebin.com",
            "https://paste.ee",
            "https://rentry.co",
            "https://ghostbin.co",
        ]
        
        # Proxy/OPSEC support — read from environment variables
        proxy_url = os.environ.get("ORACLE_PROXY", "")
        if proxy_url:
            self.session.proxies = {
                "http": proxy_url,
                "https": proxy_url,
            }
            logger.info(f"🔒 Using proxy: {proxy_url[:30]}...")
        
        # Tor SOCKS5 proxy support
        tor_proxy = os.environ.get("TOR_PROXY", "socks5://127.0.0.1:9050")
        if os.environ.get("USE_TOR", "").lower() in ("true", "1", "yes"):
            try:
                from requests.packages.urllib3.contrib.socks import SOCKSAdapter
                self.session.mount("http://", SOCKSAdapter())
                self.session.mount("https://", SOCKSAdapter())
                self.session.proxies = {
                    "http": tor_proxy,
                    "https": tor_proxy,
                }
                logger.info("🧅 Tor proxy enabled for OPSEC")
            except ImportError:
                logger.warning("⚠️  Tor support requires PySocks: pip install PySocks")
        
        # Elasticsearch backend (falls back to in-memory if unavailable)
        self.es_index = None
        try:
            from elastic_index import get_index
            self.es_index = get_index()
            logger.info(f"📦 ES backend available: {self.es_index.available}")
        except ImportError:
            logger.info("📦 elastic_index module not found — using legacy in-memory index")
        except Exception as e:
            logger.warning(f"📦 ES backend error — using in-memory: {e}")
        
        # Legacy in-memory index (fallback)
        self.index = {}  # keyword -> list of IntelligenceRecord
        self.index_by_date = {}  # date -> list of IntelligenceRecord
        self.search_history = []
    
    def random_user_agent(self) -> str:
        """Return a random User-Agent from the rotation pool."""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        ]
        import random
        return random.choice(user_agents)
    
    def search_keyword(self, keyword: str, categories: list = None, 
                       max_dorks: int = 5) -> IntelligenceReport:
        """
        Main search method — performs dorking across multiple categories
        and returns a structured intelligence report.
        """
        keyword_lower = keyword.lower().strip()
        report = IntelligenceReport(
            keyword=keyword,
            timestamp=datetime.now().isoformat(),
            records=[],
            sources=[],
        )
        
        # Determine which dork categories to use
        if categories is None:
            categories = list(self.dork_templates.keys())
        
        all_results = []
        sources_found = set()
        
        # Execute dorks for each category
        for category in categories:
            if category not in self.dork_templates:
                continue
            
            templates = self.dork_templates[category]
            dorks_to_run = templates[:max_dorks]
            
            for template in dorks_to_run:
                dork_query = template.replace("{keyword}", quote_plus(keyword))
                try:
                    results = self._execute_dork(dork_query, category, keyword)
                    for r in results:
                        all_results.append(r)
                        if r.source:
                            sources_found.add(r.source)
                    time.sleep(0.5)  # Rate limiting
                except Exception as e:
                    logger.warning(f"Dork execution error: {e}")
        
        # Process all results and extract intelligence records
        for result in all_results:
            records = self._extract_records(result, keyword)
            report.records.extend(records)
        
        # Scrape known paste sites for the keyword
        paste_records = self._scrape_paste_sites(keyword)
        report.records.extend(paste_records)
        
        # Generate statistics
        report.total_records = len(report.records)
        report.sources = list(sources_found)
        report.stats = self._generate_stats(report.records)
        
        # Store in index
        self._index_records(keyword, report.records)
        
        # Add to search history
        self.search_history.append({
            "keyword": keyword,
            "timestamp": report.timestamp,
            "total": report.total_records,
        })
        
        return report
    
    def _execute_dork(self, dork_query: str, category: str, 
                      original_keyword: str) -> list:
        """
        Execute a dork query against a search engine.
        Rotates User-Agent for anti-detection.
        Uses multiple search engine fallbacks.
        """
        results = []
        
        # Rotate User-Agent for anti-detection (each dork looks like a different browser)
        self.session.headers.update({"User-Agent": self.random_user_agent()})
        
        # Try Google (via scraping interface)
        google_url = f"https://www.google.com/search?q={quote_plus(dork_query)}&num=10"
        try:
            resp = self.session.get(google_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for g in soup.select('div.g')[:10]:
                    link = g.select_one('a')
                    title_el = g.select_one('h3')
                    snippet_el = g.select_one('div.VwiC3b')
                    if link and title_el:
                        url = link.get('href', '')
                        if url.startswith('/url?q='):
                            url = url.split('/url?q=')[1].split('&')[0]
                        results.append(DorkResult(
                            url=url,
                            title=title_el.get_text(strip=True),
                            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                            source="google",
                            discovered_at=datetime.now().isoformat(),
                            discovered_date=datetime.now().strftime("%Y-%m-%d"),
                        ))
        except Exception as e:
            logger.debug(f"Google search failed: {e}")
        
        # Try Bing as fallback with another rotated UA
        if len(results) < 3:
            self.session.headers.update({"User-Agent": self.random_user_agent()})
            try:
                bing_url = f"https://www.bing.com/search?q={quote_plus(dork_query)}&count=10"
                resp = self.session.get(bing_url, timeout=10)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for li in soup.select('li.b_algo')[:10]:
                        link = li.select_one('a')
                        snippet_el = li.select_one('.b_caption p')
                        if link:
                            results.append(DorkResult(
                                url=link.get('href', ''),
                                title=link.get_text(strip=True),
                                snippet=snippet_el.get_text(strip=True) if snippet_el else "",
                                source="bing",
                                discovered_at=datetime.now().isoformat(),
                                discovered_date=datetime.now().strftime("%Y-%m-%d"),
                            ))
            except Exception as e:
                logger.debug(f"Bing search failed: {e}")
        
        return results
    
    def _scrape_paste_sites(self, keyword: str) -> list:
        """Scrape known paste sites for the keyword"""
        records = []
        
        # Rotate UA for paste scraping too — each request looks unique
        self.session.headers.update({"User-Agent": self.random_user_agent()})
        
        # Pastebin search
        try:
            pastebin_url = f"https://www.google.com/search?q=site:pastebin.com+{quote_plus(keyword)}&num=10"
            resp = self.session.get(pastebin_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for g in soup.select('div.g')[:5]:
                    link = g.select_one('a')
                    snippet_el = g.select_one('div.VwiC3b')
                    if link:
                        url = link.get('href', '')
                        if url.startswith('/url?q='):
                            url = url.split('/url?q=')[1].split('&')[0]
                        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                        
                        # Try to fetch the actual paste content
                        try:
                            paste_resp = self.session.get(url, timeout=10)
                            if paste_resp.status_code == 200:
                                extracted = self._extract_patterns(paste_resp.text, keyword)
                                for rec in extracted:
                                    rec.source_url = url
                                    rec.source_type = "pastebin"
                                    rec.keyword = keyword
                                    records.append(rec)
                        except Exception as e:
                            logger.debug(f"Paste fetch failed: {e}")
        except Exception as e:
            logger.debug(f"Pastebin scrape failed: {e}")
        
        return records
    
    def _extract_records(self, result: DorkResult, keyword: str) -> list:
        """Extract intelligence records from a dork result by fetching the URL"""
        records = []
        
        if not result.url:
            return records
        
        try:
            resp = self.session.get(result.url, timeout=10)
            if resp.status_code == 200:
                content = resp.text
                
                # Try fetching raw content if it's a known paste/text host
                extracted = self._extract_patterns(content, keyword)
                for rec in extracted:
                    rec.source_url = result.url
                    rec.source_type = result.source
                    rec.keyword = keyword
                    rec.discovered_at = result.discovered_at
                    rec.discovered_date = result.discovered_date
                    records.append(rec)
        except Exception as e:
            logger.debug(f"Failed to fetch URL {result.url}: {e}")
        
        return records
    
    def _extract_patterns(self, content: str, keyword: str) -> list:
        """Extract all intelligence patterns from content"""
        records = []
        
        # Normalize content
        content_clean = content[:100000]  # Limit size
        
        # Extract email:password patterns
        for match in self.patterns["email_password"].finditer(content_clean):
            email, password = match.groups()
            domain = email.split('@')[-1] if '@' in email else ""
            record = IntelligenceRecord(
                id=self._generate_id(),
                record_type="email:pass",
                email=email,
                password=password[:100],
                domain=domain,
                content_preview=f"{email}:{password[:20]}***"[:200],
                severity="high",
            )
            # Validate keyword match
            if keyword.lower() in content_clean.lower()[:5000]:
                records.append(record)
        
        # Extract API keys
        for match in self.patterns["api_key"].finditer(content_clean):
            api_key = match.group(1)
            if keyword.lower() in content_clean.lower()[:5000]:
                record = IntelligenceRecord(
                    id=self._generate_id(),
                    record_type="api_key",
                    content_preview=f"API Key: {api_key[:30]}***"[:200],
                    extra_data={"api_key_prefix": api_key[:16]},
                    severity="critical",
                )
                records.append(record)
        
        # Extract IP:Port patterns
        for match in self.patterns["ip_port"].finditer(content_clean):
            ip, port = match.groups()
            if self._is_valid_ip(ip):
                if keyword.lower() in content_clean.lower()[:5000]:
                    record = IntelligenceRecord(
                        id=self._generate_id(),
                        record_type="ip:port",
                        ip_address=ip,
                        port=port,
                        content_preview=f"{ip}:{port}"[:200],
                        severity="medium",
                    )
                    records.append(record)
        
        return records
    
    def _index_records(self, keyword: str, records: list):
        """Index records for fast retrieval — uses ES when available, falls back to in-memory"""
        # Index in Elasticsearch (or memory fallback)
        if self.es_index and self.es_index.available:
            dicts = [r.to_dict() for r in records]
            self.es_index.index_bulk(dicts)
        
        # Legacy in-memory index (always keep as secondary cache)
        if keyword not in self.index:
            self.index[keyword] = []
        self.index[keyword].extend(records)
        
        for rec in records:
            date = rec.discovered_date or "unknown"
            if date not in self.index_by_date:
                self.index_by_date[date] = []
            self.index_by_date[date].append(rec)
    
    def _generate_stats(self, records: list) -> dict:
        """Generate statistics from a collection of records"""
        stats = {
            "total": len(records),
            "by_type": {},
            "by_severity": {},
            "by_domain": {},
            "unique_domains": set(),
            "emails_found": 0,
            "passwords_found": 0,
        }
        
        for rec in records:
            stats["by_type"][rec.record_type] = stats["by_type"].get(rec.record_type, 0) + 1
            stats["by_severity"][rec.severity] = stats["by_severity"].get(rec.severity, 0) + 1
            if rec.domain:
                stats["by_domain"][rec.domain] = stats["by_domain"].get(rec.domain, 0) + 1
                stats["unique_domains"].add(rec.domain)
            if rec.email:
                stats["emails_found"] += 1
            if rec.password:
                stats["passwords_found"] += 1
        stats["unique_domains"] = list(stats["unique_domains"])
        return stats
    
    def query_index(self, keyword: str = None, date_from: str = None, 
                    date_to: str = None, record_type: str = None,
                    severity: str = None, domain: str = None,
                    page: int = 1, per_page: int = 50) -> dict:
        """
        Query the indexed records with filters.
        Uses Elasticsearch full-text search when available, falls back to in-memory.
        """
        # Use Elasticsearch if available
        if self.es_index and self.es_index.available:
            from_ = (page - 1) * per_page
            es_results = self.es_index.search(
                keyword=keyword,
                record_type=record_type,
                severity=severity,
                domain=domain,
                date_from=date_from,
                date_to=date_to,
                from_=from_,
                size=per_page,
                include_stats=True,
            )
            return {
                "total": es_results["total"],
                "page": page,
                "per_page": per_page,
                "total_pages": max(1, (es_results["total"] + per_page - 1) // per_page),
                "results": es_results["results"],
                "stats": es_results["stats"],
                "took_ms": es_results["took_ms"],
                "using_elasticsearch": True,
            }
        
        # Legacy in-memory fallback
        results = []
        if keyword and keyword in self.index:
            results = self.index[keyword]
        elif date_from or date_to:
            for date, records in self.index_by_date.items():
                if date_from and date < date_from:
                    continue
                if date_to and date > date_to:
                    continue
                results.extend(records)
        else:
            for records in self.index.values():
                results.extend(records)
        
        if record_type:
            results = [r for r in results if r.record_type == record_type]
        if severity:
            results = [r for r in results if r.severity == severity]
        if domain:
            results = [r for r in results if domain.lower() in r.domain.lower()]
        
        total = len(results)
        start = (page - 1) * per_page
        end = start + per_page
        paginated = results[start:end]
        
        return {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": max(1, (total + per_page - 1) // per_page),
            "results": [r.to_dict() for r in paginated],
            "stats": self._generate_stats(results),
            "using_elasticsearch": False,
        }
    
    def get_search_history(self) -> list:
        """Return search history"""
        return self.search_history
    
    def get_index_stats(self) -> dict:
        """Return overall index statistics — uses ES aggregations when available"""
        if self.es_index and self.es_index.available:
            try:
                es_stats = self.es_index.get_stats()
                return {
                    "total_keywords": len(es_stats.get("by_type", {})),
                    "total_records": es_stats.get("total_records", 0),
                    "total_searches": len(self.search_history),
                    "critical_count": es_stats.get("critical_count", 0),
                    "by_type": es_stats.get("by_type", {}),
                    "by_severity": es_stats.get("by_severity", {}),
                    "by_domain": es_stats.get("by_domain", {}),
                    "by_source": es_stats.get("by_source", {}),
                    "by_year": es_stats.get("by_year", {}),
                    "using_elasticsearch": True,
                }
            except Exception as e:
                logger.warning(f"ES stats error: {e}")
        
        # Legacy fallback
        total = sum(len(v) for v in self.index.values())
        return {
            "total_keywords": len(self.index),
            "total_records": total,
            "total_searches": len(self.search_history),
            "date_coverage": sorted(self.index_by_date.keys()),
        }
    
    def _generate_id(self) -> str:
        """Generate a unique record ID"""
        raw = f"{time.time_ns()}{id(self)}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]
    
    def _is_valid_ip(self, ip: str) -> bool:
        """Validate an IP address"""
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            return False


# ─── Sample Data Generator (for demo/development) ────────────

class SampleDataGenerator:
    """Generates realistic sample intelligence data for demo purposes"""
    
    SAMPLE_DOMAINS = [
        "comcast.net", "xfinity.com", "gmail.com", "yahoo.com", 
        "hotmail.com", "outlook.com", "aol.com", "verizon.net",
        "att.net", "sbcglobal.net", "msn.com", "live.com",
        "icloud.com", "protonmail.com", "mail.com",
    ]
    
    SAMPLE_COMPANIES = [
        "Comcast", "AT&T", "Verizon", "T-Mobile", "Charter Spectrum",
        "Cox Communications", "Optimum", "Mediacom", "WOW!",
        "Frontier Communications", "CenturyLink", "Xfinity",
    ]
    
    SAMPLE_RECORD_TYPES = ["email:pass", "user:pass", "api_key", "ip:port", "hash", "config"]
    
    @staticmethod
    def generate_records(keyword: str, count: int = 25) -> list:
        """Generate sample intelligence records for a keyword"""
        import random
        random.seed(hash(keyword) % (2**32))
        
        records = []
        base_time = datetime.now() - timedelta(days=random.randint(0, 365))
        
        for i in range(count):
            # Pick a domain related to the keyword or random
            domain = keyword.lower().replace(" ", "") + ".com"
            if random.random() > 0.4:
                domain = random.choice(SampleDataGenerator.SAMPLE_DOMAINS)
            
            username = f"user{random.randint(1000, 9999)}"
            email = f"{username}@{domain}"
            password_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%"
            password = ''.join(random.choice(password_chars) for _ in range(random.randint(8, 20)))
            
            record_date = base_time + timedelta(days=i * random.randint(1, 14))
            severity = random.choices(
                ["critical", "high", "medium", "low", "info"],
                weights=[5, 20, 35, 25, 15]
            )[0]
            
            record_type = random.choice(SampleDataGenerator.SAMPLE_RECORD_TYPES)
            
            rec = IntelligenceRecord(
                id=hashlib.md5(f"{email}{password}{i}".encode()).hexdigest()[:12],
                keyword=keyword,
                source_url=f"https://paste.example.com/{random.randint(100000, 999999)}",
                source_type=random.choice(["pastebin", "github", "public_directory", "shodan", "telegram"]),
                record_type=record_type,
                content_preview=f"{email}:{password[:10]}***",
                discovered_at=record_date.isoformat(),
                discovered_date=record_date.strftime("%Y-%m-%d"),
                severity=severity,
                domain=domain,
                email=email,
                username=username,
                password=password if record_type == "email:pass" else "",
                ip_address=f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
                port=str(random.choice([22, 80, 443, 3306, 5432, 6379, 8080, 8443])),
                extra_data={
                    "source_confidence": round(random.uniform(0.3, 0.95), 2),
                    "verified": random.choice([True, False]),
                    "year_found": record_date.year,
                }
            )
            records.append(rec)
        
        return records


# ─── Integration with Intel Connectors ─────────────────────

def get_intel_orchestrator():
    """Lazy-load the IntelOrchestrator to avoid import failures."""
    try:
        from intel_connectors import IntelOrchestrator
        return IntelOrchestrator()
    except ImportError:
        logger.warning("Intel connectors not available (intel_connectors.py not found)")
        return None
    except Exception as e:
        logger.warning(f"Intel connectors init failed: {e}")
        return None

# Enhanced search with external APIs
class EnhancedOracleEngine:
    """Wraps OracleEngine and IntelOrchestrator for unified intelligence."""
    
    def __init__(self):
        self.base_engine = OracleEngine()
        self.intel = get_intel_orchestrator()
    
    def search(self, keyword: str, use_apis: bool = True, 
               categories: list = None, sample: bool = False) -> dict:
        """
        Unified search — combines OSINT dorking with external API intelligence.
        
        Returns: {
            "keyword", "timestamp",
            "dorking": { ... from OracleEngine ... },
            "api_intel": { ... from IntelOrchestrator ... },
            "summary": { total_records, sources, critical_count }
        }
        """
        keyword = keyword.strip()
        
        # 1. Run base OSINT dorking
        if sample:
            sample_records = SampleDataGenerator.generate_records(keyword, 40)
            dorking = {
                "keyword": keyword,
                "total_records": len(sample_records),
                "records": [r.to_dict() for r in sample_records[:100]],
                "sources": ["sample_data"],
                "stats": self.base_engine._generate_stats(sample_records),
            }
        else:
            report = self.base_engine.search_keyword(keyword, categories=categories)
            dorking = {
                "keyword": report.keyword,
                "total_records": report.total_records,
                "records": [r.to_dict() for r in report.records[:100]],
                "sources": report.sources,
                "stats": report.stats,
            }
        
        # 2. Run external API intelligence (if available and requested)
        api_intel = None
        if use_apis and self.intel:
            try:
                api_intel = self.intel.investigate_keyword(keyword)
            except Exception as e:
                logger.error(f"API intel error: {e}")
        
        # 3. Combine summary
        total = dorking.get("total_records", 0)
        sources = dorking.get("sources", [])
        critical_count = dorking.get("stats", {}).get("by_severity", {}).get("critical", 0)
        
        if api_intel:
            total += api_intel["summary"].get("total_findings", 0)
            critical_count += api_intel["summary"].get("critical_findings", 0)
        
        return {
            "keyword": keyword,
            "timestamp": datetime.now().isoformat(),
            "dorking": dorking,
            "api_intel": api_intel,
            "summary": {
                "total_records": total,
                "critical_count": critical_count,
                "sources": sources + (api_intel["summary"]["apis_queried"] if api_intel else []),
                "apis_available": self.intel.available_apis if self.intel else [],
            }
        }


# ─── CLI Entry Point ─────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    engine = OracleEngine()
    
    if len(sys.argv) > 1:
        keyword = sys.argv[1]
        print(f"🔍 Searching for: {keyword}")
        report = engine.search_keyword(keyword)
        print(f"\n📊 Report for '{keyword}':")
        print(f"   Total records: {report.total_records}")
        print(f"   Sources found: {', '.join(report.sources)}")
        print(f"   Stats: {json.dumps(report.stats, indent=2, default=str)}")
        
        if report.records:
            print(f"\n📝 Sample records:")
            for rec in report.records[:5]:
                print(f"   [{rec.severity.upper()}] {rec.record_type}: {rec.content_preview}")
    else:
        print("Usage: python oracle_engine.py <keyword>")
        print("Example: python oracle_engine.py comcast")
