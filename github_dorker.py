"""
╔══════════════════════════════════════════════════════════════╗
║  GITHUB DORKER — Credential Mining from Public Repos        ║
║                                                              ║
║  Busca en GitHub:                                            ║
║  1. Código fuente: email:password en repositorios públicos  ║
║  2. Gists públicos: combos compartidos como gist            ║
║  3. Issues/PRs: credenciales en discusiones públicas        ║
║  4. Commits: passwords commiteadas por error                ║
║                                                              ║
║  API gratuita: 10 req/min (sin token), 30 req/min (con token)║
║  Token opcional: GITHUB_TOKEN env var para mayor rate limit  ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import re
import json
import time
import base64
import logging
import random
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import quote_plus

import requests

from combo_leecher_engine import ComboParser, ComboEntry, RateLimiter, random_ua

logger = logging.getLogger("GitHubDorker")

# ─── GitHub Search API endpoints ────────────────────────────

GITHUB_API = "https://api.github.com"
GITHUB_SEARCH_CODE = f"{GITHUB_API}/search/code"
GITHUB_SEARCH_REPO = f"{GITHUB_API}/search/repositories"
GITHUB_SEARCH_ISSUES = f"{GITHUB_API}/search/issues"
GITHUB_GISTS = f"{GITHUB_API}/gists"

# ─── GitHub dork queries ───────────────────────────────────

CODE_DORKS = [
    # Config files with passwords
    '"password" "{keyword}" extension:env',
    '"password" "{keyword}" extension:cfg',
    '"password" "{keyword}" extension:conf',
    '"password" "{keyword}" extension:config',
    '"password" "{keyword}" extension:ini',
    '"password" "{keyword}" extension:yml extension:yaml',
    '"password" "{keyword}" extension:xml',
    '"passwd" "{keyword}" extension:txt',
    # Credential files
    '"email:pass" "{keyword}" extension:txt',
    '"email:password" "{keyword}" extension:txt',
    '"user:pass" "{keyword}" extension:txt',
    '"username:password" "{keyword}"',
    '{keyword} "dump" "email" "password" extension:txt',
    '{keyword} "combo" extension:txt extension:csv',
    '{keyword} "leaked" extension:txt extension:csv',
    '{keyword} "credentials" extension:txt extension:csv',
    # SQL dumps
    '{keyword} "INSERT INTO" "password" extension:sql',
    '{keyword} "VALUES" "email" "pass" extension:sql',
    # JSON configs
    '{keyword} "password" extension:json "email"',
    '{keyword} "\"password\"" extension:json "\"email\""',
    # Log files
    '{keyword} extension:log "password" "@"',
    '{keyword} extension:log "login" "failed"',
    # Backup files
    '{keyword} extension:bak extension:old extension:backup',
    # Database files
    '{keyword} extension:db extension:sqlite extension:sqlite3',
    # Python files with hardcoded creds
    '{keyword} "password =" extension:py',
    '{keyword} "login =" extension:py',
    # JavaScript with API keys
    '{keyword} "apiKey" extension:js "{keyword}"',
    '{keyword} "api_key" extension:py',
    # PHP with DB credentials
    r'{keyword} "$password" extension:php',
    r'{keyword} "$db_password" extension:php',
]

ISSUE_DORKS = [
    '{keyword} "email:pass"',
    '{keyword} "email:password"',
    '{keyword} combo comment:"email:pass"',
    '{keyword} comment:"password" "leak"',
    '{keyword} "credentials" "dump"',
    '{keyword} "breach" "password"',
    '{keyword} "leaked" in:body',
]

REPO_DORKS = [
    '{keyword} combo list',
    '{keyword} leaked database',
    '{keyword} credential dump',
    '{keyword} password dump',
]


# ═══════════════════════════════════════════════════════════════
#  GITHUB DORKER
# ═══════════════════════════════════════════════════════════════

class GitHubDorker:
    """
    Search GitHub for credential combos using the public Search API.

    Estrategias de búsqueda:
    1. Code Search - busca en archivos dentro de repos públicos
    2. Gist Search - busca en gists públicos (a menudo usados para leaks)
    3. Issue/PR Search - busca en issues y pull requests
    4. Repo Search - descubre repos que pueden contener combos

    Rate limits (por IP):
    - Sin token: 10 requests/minuto
    - Con GITHUB_TOKEN: 30 requests/minuto, 5,000 requests/hora

    Args:
        token: GitHub personal access token (opcional, de GITHUB_TOKEN env var)
    """

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "OracleIntel/2.0 (github-dorker)",
        })
        if self.token:
            self.session.headers["Authorization"] = f"token {self.token}"
            self.rate_limit = 30  # req/min con token
            logger.info("🐙 GitHub Dorker: Authenticated (30 req/min)")
        else:
            self.rate_limit = 10  # req/min sin token
            logger.info("🐙 GitHub Dorker: Unauthenticated (10 req/min)")
            logger.info("   Set GITHUB_TOKEN env var for 30 req/min")

        self.rate_limiter = RateLimiter(requests_per_minute=self.rate_limit)
        self.parser = ComboParser()
        self.stats = {
            "code_searches": 0,
            "gist_searches": 0,
            "issue_searches": 0,
            "files_fetched": 0,
            "gists_fetched": 0,
            "total_combos": 0,
        }

    # ─── Rate Limit Check ─────────────────────────────────

    def _check_rate_limit(self) -> dict:
        """Check remaining GitHub API rate limit."""
        try:
            resp = self.session.get(f"{GITHUB_API}/rate_limit", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                core = data.get("resources", {}).get("core", {})
                search = data.get("resources", {}).get("search", {})
                return {
                    "core_remaining": core.get("remaining", 0),
                    "core_limit": core.get("limit", 0),
                    "search_remaining": search.get("remaining", 0),
                    "search_limit": search.get("limit", 0),
                    "reset": search.get("reset", 0),
                }
        except Exception:
            pass
        return {}

    # ─── Search GitHub Code ────────────────────────────────

    def search_code(self, keyword: str, max_results: int = 30) -> List[ComboEntry]:
        """
        Search GitHub code repositories for credential combos.

        Busca en el código fuente de repositorios públicos por patrones
        de email:password, configs con credenciales, dumps SQL, etc.

        Args:
            keyword: Search term (e.g., "comcast")
            max_results: Max files to fetch and parse

        Returns:
            List of ComboEntry objects
        """
        all_combos = []
        seen_urls = set()

        # Seleccionar dorks relevantes al keyword
        dorks = random.sample(CODE_DORKS, min(8, len(CODE_DORKS)))

        for dork_template in dorks:
            self.rate_limiter.wait(source="github_code")
            dork = dork_template.replace("{keyword}", keyword)

            try:
                resp = self.session.get(
                    GITHUB_SEARCH_CODE,
                    params={"q": dork, "per_page": min(max_results, 30)},
                    timeout=10,
                )

                if resp.status_code == 403:
                    logger.warning("🐙 GitHub rate limit reached (code search)")
                    break
                if resp.status_code != 200:
                    continue

                self.stats["code_searches"] += 1
                data = resp.json()
                total_count = data.get("total_count", 0)
                items = data.get("items", [])

                if total_count == 0:
                    continue

                logger.debug(f"🐙 Code search '{dork[:40]}...': {total_count} results")

                for item in items[:max_results]:
                    # Get file URL
                    html_url = item.get("html_url", "")
                    if html_url in seen_urls:
                        continue
                    seen_urls.add(html_url)

                    # Try to get raw content
                    raw_url = item.get("raw_url", "") or item.get("git_url", "")
                    content = self._fetch_raw(raw_url)

                    if content:
                        self.stats["files_fetched"] += 1
                        repo_name = item.get("repository", {}).get("full_name", "")
                        path = item.get("path", "")

                        combos = self.parser.parse_text(
                            content,
                            source_url=html_url,
                            source_type="github_code",
                            keyword=keyword,
                        )

                        # Extra data: repository info
                        for c in combos:
                            c.extra_data["github_repo"] = repo_name
                            c.extra_data["github_path"] = path

                        all_combos.extend(combos)

            except Exception as e:
                logger.debug(f"🐙 Code search error: {e}")

            time.sleep(1)  # Additional safety delay

        self.stats["total_combos"] += len(all_combos)
        logger.info(f"🐙 GitHub code search: {len(all_combos)} combos for '{keyword}'")
        return all_combos

    # ─── Search Gists ──────────────────────────────────────

    def search_gists(self, keyword: str, max_gists: int = 30) -> List[ComboEntry]:
        """
        Search public GitHub Gists for credential combos.

        Los gists son comúnmente usados para compartir listas de combos
        porque son fáciles de crear y difíciles de rastrear.

        Args:
            keyword: Search term
            max_gists: Max gists to fetch

        Returns:
            List of ComboEntry objects
        """
        all_combos = []

        # GitHub Gist Search API (separate from code search)
        self.rate_limiter.wait(source="github_gists")

        try:
            resp = self.session.get(
                GITHUB_SEARCH_CODE,  # Code search also covers gists
                params={"q": f"{keyword} gist", "per_page": min(max_gists, 30)},
                timeout=10,
            )

            if resp.status_code != 200:
                return all_combos

            self.stats["gist_searches"] += 1
            items = resp.json().get("items", [])

            for item in items[:max_gists]:
                html_url = item.get("html_url", "")
                if "gist.github.com" not in html_url:
                    continue

                raw_url = item.get("raw_url", "")
                content = self._fetch_raw(raw_url)

                if content:
                    self.stats["gists_fetched"] += 1
                    combos = self.parser.parse_text(
                        content,
                        source_url=html_url,
                        source_type="github_gist",
                        keyword=keyword,
                    )

                    for c in combos:
                        c.extra_data["github_gist"] = True
                        filename = item.get("name", "")
                        c.extra_data["gist_filename"] = filename

                    all_combos.extend(combos)

        except Exception as e:
            logger.debug(f"🐙 Gist search error: {e}")

        # Also try direct gist scraping (GitHub gists search)
        self.rate_limiter.wait(source="github_gists_direct")
        try:
            # Search gists with keyword in description/content
            resp = self.session.get(
                f"{GITHUB_GISTS}/public",
                params={"per_page": min(max_gists, 100)},
                timeout=10,
            )

            if resp.status_code == 200:
                gists = resp.json()
                for gist in gists:
                    description = gist.get("description", "") or ""
                    if keyword.lower() not in description.lower():
                        continue

                    files = gist.get("files", {})
                    for filename, file_info in files.items():
                        raw_url = file_info.get("raw_url", "")
                        if raw_url:
                            content = self._fetch_raw(raw_url)
                            if content:
                                combos = self.parser.parse_text(
                                    content,
                                    source_url=gist.get("html_url", ""),
                                    source_type="github_gist",
                                    keyword=keyword,
                                )
                                all_combos.extend(combos)

        except Exception as e:
            logger.debug(f"🐙 Gist direct search error: {e}")

        self.stats["total_combos"] += len(all_combos)
        logger.info(f"🐙 GitHub gist search: {len(all_combos)} combos for '{keyword}'")
        return all_combos

    # ─── Search Issues ─────────────────────────────────────

    def search_issues(self, keyword: str, max_issues: int = 20) -> List[ComboEntry]:
        """
        Search GitHub Issues and PRs for credential combos.

        A menudo se comparten credenciales en issues/comentarios de repos
        públicos, especialmente en repos de testing/demo.

        Args:
            keyword: Search term
            max_issues: Max issues to fetch

        Returns:
            List of ComboEntry objects
        """
        all_combos = []
        seen = set()

        dorks = random.sample(ISSUE_DORKS, min(4, len(ISSUE_DORKS)))

        for dork_template in dorks:
            self.rate_limiter.wait(source="github_issues")
            dork = dork_template.replace("{keyword}", keyword)

            try:
                resp = self.session.get(
                    GITHUB_SEARCH_ISSUES,
                    params={"q": dork, "per_page": min(max_issues, 30)},
                    timeout=10,
                )

                if resp.status_code != 200:
                    continue

                self.stats["issue_searches"] += 1
                items = resp.json().get("items", [])

                for item in items:
                    body = item.get("body", "") or ""
                    title = item.get("title", "") or ""
                    full_text = f"{title} {body}"

                    # Parse body for combos
                    combos = self.parser.parse_text(
                        full_text,
                        source_url=item.get("html_url", ""),
                        source_type="github_issue",
                        keyword=keyword,
                    )

                    for c in combos:
                        key = f"{c.email}:{c.password}"
                        if key not in seen:
                            seen.add(key)
                            all_combos.append(c)

            except Exception as e:
                logger.debug(f"🐙 Issue search error: {e}")

            time.sleep(1)

        logger.info(f"🐙 GitHub issue search: {len(all_combos)} combos for '{keyword}'")
        return all_combos

    # ─── Discover Repos ────────────────────────────────────

    def discover_repos(self, keyword: str, max_repos: int = 10) -> List[Dict[str, Any]]:
        """
        Discover GitHub repositories that might contain credential data.

        No extrae combos directamente, sino que identifica repos
        que merecen una inspección más profunda.

        Args:
            keyword: Search term
            max_repos: Max repos to return

        Returns:
            List of repo dicts with name, url, stars, description
        """
        repos = []

        for dork_template in REPO_DORKS:
            self.rate_limiter.wait(source="github_repos")
            dork = dork_template.replace("{keyword}", keyword)

            try:
                resp = self.session.get(
                    GITHUB_SEARCH_REPO,
                    params={"q": dork, "sort": "updated", "per_page": min(max_repos, 20)},
                    timeout=10,
                )

                if resp.status_code != 200:
                    continue

                items = resp.json().get("items", [])
                for repo in items[:max_repos]:
                    repos.append({
                        "name": repo.get("full_name", ""),
                        "url": repo.get("html_url", ""),
                        "description": (repo.get("description") or "")[:200],
                        "stars": repo.get("stargazers_count", 0),
                        "updated": repo.get("updated_at", ""),
                        "topics": repo.get("topics", []),
                    })

            except Exception as e:
                logger.debug(f"🐙 Repo search error: {e}")

            time.sleep(1)

        return repos

    # ─── Fetch Raw Content ─────────────────────────────────

    def _fetch_raw(self, url: str) -> Optional[str]:
        """Fetch raw content from a URL (handles GitHub raw URLs)."""
        if not url:
            return None

        try:
            self.rate_limiter.wait(source="github_fetch")
            resp = self.session.get(url, timeout=10)

            if resp.status_code != 200:
                return None

            content_type = resp.headers.get("content-type", "")

            # If JSON, decode base64 content (GitHub API blob format)
            if content_type.startswith("application/json") or content_type.startswith("text/json"):
                try:
                    data = resp.json()
                    content = data.get("content", "")
                    if content:
                        decoded = base64.b64decode(content).decode("utf-8", errors="ignore")
                        return decoded[:500000]
                except Exception:
                    pass
                # If no content field, return raw text
                if len(resp.text) > 20:
                    return resp.text[:500000]
                return None

            # Raw content (plain text, HTML, etc.)
            if len(resp.text) > 20:
                return resp.text[:500000]

        except Exception as e:
            logger.debug(f"🐙 Fetch error {url[:50]}: {e}")

        return None

    # ─── Scrape All ────────────────────────────────────────

    def scrape_all(self, keyword: str, max_per_source: int = 20) -> List[ComboEntry]:
        """
        Run ALL GitHub search strategies for a keyword.

        Orden:
        1. Code search (highest value)
        2. Gist search (often has combos)
        3. Issues search (lower value but easy)

        Args:
            keyword: Search term
            max_per_source: Max results per source

        Returns:
            Deduplicated list of ComboEntry
        """
        all_combos = []
        seen = set()

        # 1. Code search
        logger.info(f"🐙 Searching GitHub CODE for '{keyword}'...")
        code_combos = self.search_code(keyword, max_results=max_per_source)
        for c in code_combos:
            key = f"{c.email}:{c.password}"
            if key not in seen:
                seen.add(key)
                all_combos.append(c)

        time.sleep(1)

        # 2. Gist search
        logger.info(f"🐙 Searching GitHub GISTS for '{keyword}'...")
        gist_combos = self.search_gists(keyword, max_gists=max_per_source)
        for c in gist_combos:
            key = f"{c.email}:{c.password}"
            if key not in seen:
                seen.add(key)
                all_combos.append(c)

        time.sleep(1)

        # 3. Issues search
        logger.info(f"🐙 Searching GitHub ISSUES for '{keyword}'...")
        issue_combos = self.search_issues(keyword, max_issues=max_per_source)
        for c in issue_combos:
            key = f"{c.email}:{c.password}"
            if key not in seen:
                seen.add(key)
                all_combos.append(c)

        logger.info(f"🐙 GitHub total: {len(all_combos)} unique combos for '{keyword}'")
        return all_combos

    # ─── Stats ─────────────────────────────────────────────

    def get_stats(self) -> dict:
        """Get GitHub Dorker statistics."""
        rate = self._check_rate_limit()
        return {
            **self.stats,
            "token_configured": bool(self.token),
            "rate_limit_per_min": self.rate_limit,
            "remaining": rate.get("search_remaining", "unknown"),
        }


# ═══════════════════════════════════════════════════════════════
#  CLI TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else "comcast"
    source = sys.argv[2] if len(sys.argv) > 2 else "all"

    dorker = GitHubDorker()
    print(f"\n🐙 GITHUB DORKER v1.0")
    print(f"🔍 Keyword: {keyword}")
    print(f"📡 Source: {source}")
    print(f"🔑 Token: {'✅' if dorker.token else '❌ No (10 req/min)'}")
    print(f"{'─' * 50}")

    if source == "code":
        combos = dorker.search_code(keyword)
    elif source == "gists":
        combos = dorker.search_gists(keyword)
    elif source == "issues":
        combos = dorker.search_issues(keyword)
    elif source == "repos":
        repos = dorker.discover_repos(keyword)
        print(f"\n📦 Discovered {len(repos)} repos:")
        for r in repos:
            print(f"   📂 {r['name']} ⭐{r['stars']}")
        combos = []
    else:
        combos = dorker.scrape_all(keyword)

    print(f"\n✅ Total combos: {len(combos)}")
    for combo in combos[:10]:
        pw = combo.password[:10] + "***" if len(combo.password) > 10 else combo.password
        src = combo.extra_data.get("github_repo", "") or combo.extra_data.get("github_gist", "")
        src_str = f" [{src}]" if src else ""
        print(f"   📧 {combo.email:<35} : {pw:<15}{src_str}")

    print(f"\n📊 Stats: {dorker.get_stats()}")
