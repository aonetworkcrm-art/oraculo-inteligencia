#!/usr/bin/env python
"""
╔══════════════════════════════════════════════════════════════╗
║  ORÁCULO DE INTELIGENCIA — Launch App                       ║
║                                                              ║
║  Uso:                                                       ║
║    python run.py                    # Iniciar API server    ║
║    python run.py --desktop          # Iniciar Desktop app   ║
║    python run.py --telegram-login   # Login a Telegram      ║
║    python run.py --dump comcast     # CLI Dump Finder        ║
║    python run.py --leech comcast    # CLI Combo Leecher      ║
║    python run.py --search comcast   # CLI OSINT Search      ║
║    python run.py --proxy-scrape     # CLI Proxy Scraper      ║
║    python run.py --proxy-test       # CLI Proxy Tester      ║
║    python run.py --check-apis       # Verificar APIs         ║
║    python run.py --export key.txt   # Exportar datos        ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import sys
import argparse
import json
import logging
from datetime import datetime

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env if available
try:
    from dotenv import load_dotenv
    dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("OracleLauncher")


def start_server(port=None):
    """Start the Flask API server."""
    port = port or int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")

    logger.info(f"🚀 Starting Oracle Intelligence API on port {port}")

    # Import and run
    from api import app, socketio
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)


def start_desktop():
    """Start the desktop application."""
    logger.info("🖥️ Starting Oracle Intelligence Desktop App")
    from desktop_app import main
    main()


def cli_search(keyword):
    """CLI search."""
    from oracle_engine import EnhancedOracleEngine

    engine = EnhancedOracleEngine()
    print(f"\n🔍 Searching for: {keyword}\n")
    result = engine.search(keyword)

    total = result.get("summary", {}).get("total_records", 0)
    critical = result.get("summary", {}).get("critical_count", 0)
    apis = result.get("summary", {}).get("apis_available", [])

    print(f"📊 Results: {total} records ({critical} critical)")
    print(f"🔌 APIs available: {', '.join(apis) or 'none'}")

    for rec in result.get("all_records", [])[:10]:
        sev = rec.get("severity", "info")
        email = rec.get("email", rec.get("username", ""))
        domain = rec.get("domain", "")
        source = rec.get("source_type", "")
        print(f"  [{sev.upper():8}] {email:<35} @{domain:<15} via {source}")

    print(f"\n✅ Search complete in {result.get('timestamp', '')[:19]}")


def cli_dump(keyword, year=None, month=None):
    """CLI dump finder."""
    from dump_finder import DumpFinder

    finder = DumpFinder()
    print(f"\n🗄️ Dump Finder for: {keyword}\n")

    result = finder.search_fast(keyword, year=year, month=month)

    print(f"📊 Dorks: {result.get('dorks_executed', 0)}")
    print(f"🔗 URLs found: {result.get('urls_found', 0)}")
    print(f"📥 URLs fetched: {result.get('urls_fetched', 0)}")
    print(f"🔐 Combos: {result.get('filtered_combos_count', 0)}")
    print(f"⏱️ Time: {result.get('took_seconds', 0)}s")

    for c in result.get("combos_sample", [])[:10]:
        pw = c.get("password", "")
        pw_display = pw[:12] + "***" if len(pw) > 12 else pw
        print(f"  📧 {c.get('email',''):<35} : {pw_display:<15} [{c.get('domain','')}]")

    files = result.get("files_saved", {}).get("files_created", [])
    if files:
        print(f"\n💾 Saved files:")
        for f in files:
            print(f"  📄 {f}")

    print(f"\n✅ Dump complete")


def cli_leech(keyword):
    """CLI combo leech."""
    from combo_leecher_engine import ComboLeecherEngine

    engine = ComboLeecherEngine()
    print(f"\n🔐 Leeching combos for: {keyword}\n")

    result = engine.leech(keyword)

    print(f"📊 Total: {result.total}")
    print(f"✅ Valid: {result.valid_count}")
    print(f"❌ Invalid: {result.invalid_count}")
    print(f"📡 Sources: {', '.join(result.sources)}")
    print(f"⏱️ Time: {result.took_seconds:.1f}s")

    for combo in result.combos[:10]:
        pw = combo.password[:10] + "***" if len(combo.password) > 10 else combo.password
        print(f"  {combo.email:<35} : {pw:<15} [{combo.domain}] via {combo.source_type}")

    print(f"\n✅ Leech complete")


def cli_proxy(action):
    """CLI proxy operations."""
    from proxy_engine import ProxyEngine

    engine = ProxyEngine()
    print(f"\n🌐 Proxy Engine — {action}\n")

    if action == "scrape":
        result = engine.scrape_proxies()
        print(f"🕸️ Scraped {result['total']} proxies from {len(result['by_source'])} sources")

    elif action == "test":
        result = engine.test_proxies()
        pool = result if "alive" in result else engine.get_stats().get("pool", {})
        print(f"✅ Test complete")

    stats = engine.get_stats()
    pool = stats.get("pool", {})
    print(f"\n📊 Pool stats:")
    print(f"  Total: {pool.get('total', 0)}")
    print(f"  Alive: {pool.get('alive', 0)}")
    print(f"  Dead: {pool.get('dead', 0)}")
    print(f"  Untested: {pool.get('untested', 0)}")


def cli_check_apis():
    """Check which APIs are configured."""
    from intel_connectors import IntelOrchestrator

    orch = IntelOrchestrator()
    print(f"\n🔌 API Status:\n")
    
    apis = {
        "shodan": {"key": "SHODAN_API_KEY", "connected": False},
        "hunter": {"key": "HUNTER_API_KEY", "connected": False},
        "hibp": {"key": "HIBP_API_KEY", "connected": False},
        "virustotal": {"key": "VT_API_KEY", "connected": False},
        "censys": {"key": "CENSYS_TOKEN", "connected": False},
    }

    for api_name, info in apis.items():
        configured = getattr(orch, api_name, None)
        if configured:
            enabled = configured.enabled if hasattr(configured, 'enabled') else False
        else:
            enabled = False
        status = "✅ CONFIGURADA" if enabled else "❌ NO CONFIGURADA"
        print(f"  {api_name:12} [{status}]  (env: {info['key']})")

    print(f"\n  APIs disponibles: {', '.join(orch.available_apis) if orch.available_apis else 'ninguna'}")
    print(f"  Total: {len(orch.available_apis)}/5")


def cli_telegram_login():
    """Login to Telegram."""
    print("\n💬 Telegram Login\n")
    print("This will create a .session file for Telethon.")
    print("Make sure TG_API_ID and TG_API_HASH are set in .env\n")
    
    from telegram_scraper import cli_login
    cli_login()


def cli_github(keyword):
    """CLI GitHub Dorker."""
    from github_dorker import GitHubDorker

    dorker = GitHubDorker()
    print(f"\n🐙 GitHub Dorker for: {keyword}\n")
    print(f"🔑 Token: {'✅' if dorker.token else '❌ Sin token (10 req/min)'}")
    if not dorker.token:
        print("   Sugerencia: set GITHUB_TOKEN env var para 30 req/min")
    print()

    combos = dorker.scrape_all(keyword, max_per_source=15)

    print(f"\n📊 Total: {len(combos)}")
    for combo in combos[:10]:
        pw = combo.password[:10] + "***" if len(combo.password) > 10 else combo.password
        repo = combo.extra_data.get("github_repo", "")
        src_str = f" [{repo}]" if repo else ""
        print(f"  📧 {combo.email:<35} : {pw:<15}{src_str}")

    if len(combos) > 10:
        print(f"\n   ... y {len(combos) - 10} mas")

    print(f"\n📊 Stats: {dorker.get_stats()}")
    print(f"\n✅ GitHub search complete")


def cli_telegram_search(keyword):
    """Search Telegram for credential combos."""
    from telegram_scraper import TelegramIntelScraper
    
    scraper = TelegramIntelScraper()
    
    if not scraper.enabled:
        print("❌ Telegram not configured. Set TG_API_ID and TG_API_HASH in .env")
        print("   Get them from https://my.telegram.org/apps")
        print("   Then run: python run.py --telegram-login")
        return
    
    print(f"\n💬 Searching Telegram for '{keyword}'...")
    print("=" * 50)
    
    combos = scraper.scrape(keyword)
    
    print(f"\n✅ Found {len(combos)} combos:")
    for combo in combos[:20]:
        pw_hidden = combo.password[:10] + "***" if len(combo.password) > 10 else combo.password
        print(f"   📧 {combo.email:<40} : {pw_hidden:<15} [{combo.domain}]")
    
    if len(combos) > 20:
        print(f"\n   ... and {len(combos) - 20} more")
    
    print(f"\n📊 Stats: {scraper.get_stats()}")


def main():
    parser = argparse.ArgumentParser(
        description="🛸 Oráculo de Inteligencia — Threat Intelligence OSINT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run.py                    # Iniciar API server
  python run.py --desktop           # Iniciar Desktop App
  python run.py --search comcast    # Búsqueda OSINT
  python run.py --dump comcast      # Dump Finder
  python run.py --leech comcast     # Combo Leecher
  python run.py --proxy-scrape      # Scrape Proxies
  python run.py --proxy-test        # Test Proxies
  python run.py --check-apis        # Verificar APIs
  python run.py --telegram-login    # Login Telegram
        """
    )

    parser.add_argument("--desktop", action="store_true", help="Iniciar aplicación de escritorio")
    parser.add_argument("--port", type=int, default=None, help="Puerto para el servidor API")
    parser.add_argument("--search", type=str, default=None, metavar="KEYWORD", help="Búsqueda OSINT")
    parser.add_argument("--dump", type=str, default=None, metavar="KEYWORD", help="Dump Finder")
    parser.add_argument("--year", type=int, default=None, help="Año para Dump Finder")
    parser.add_argument("--month", type=int, default=None, help="Mes para Dump Finder (1-12)")
    parser.add_argument("--leech", type=str, default=None, metavar="KEYWORD", help="Combo Leecher")
    parser.add_argument("--proxy-scrape", action="store_true", help="Scrape proxies")
    parser.add_argument("--proxy-test", action="store_true", help="Test proxies")
    parser.add_argument("--check-apis", action="store_true", help="Verificar APIs configuradas")
    parser.add_argument("--telegram-login", action="store_true", help="Login a Telegram")
    parser.add_argument("--telegram-search", type=str, default=None, metavar="KEYWORD", help="Search Telegram for combos")
    parser.add_argument("--github", type=str, default=None, metavar="KEYWORD", help="GitHub Dorking")
    parser.add_argument("--version", action="store_true", help="Mostrar versión")

    args = parser.parse_args()

    if args.version:
        print("🛸 Oráculo de Inteligencia v1.0.0")
        print("Threat Intelligence OSINT Platform")
        print("Python " + sys.version.split()[0])
        return

    if args.desktop:
        start_desktop()
    elif args.search:
        cli_search(args.search)
    elif args.dump:
        cli_dump(args.dump, year=args.year, month=args.month)
    elif args.leech:
        cli_leech(args.leech)
    elif args.proxy_scrape:
        cli_proxy("scrape")
    elif args.proxy_test:
        cli_proxy("test")
    elif args.check_apis:
        cli_check_apis()
    elif args.github:
        cli_github(args.github)
    elif args.telegram_search:
        cli_telegram_search(args.telegram_search)
    elif args.telegram_login:
        cli_telegram_login()
    else:
        start_server(port=args.port)


if __name__ == "__main__":
    main()
