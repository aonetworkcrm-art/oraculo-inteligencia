"""
╔══════════════════════════════════════════════════════════════╗
║  ORÁCULO DE INTELIGENCIA — API Server v2.0                   ║
║  Flask REST API + External API Connectors                    ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import json
import logging
import time
import platform
import multiprocessing
from datetime import datetime

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

from oracle_engine import OracleEngine, SampleDataGenerator, EnhancedOracleEngine

# Use local API keys (env var → file fallback)
from local_keys import (
    get_shodan_key, get_hunter_key, get_hibp_key,
    get_vt_key, get_censys_token,
)

# Dump Finder
from dump_finder import DumpFinder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OracleAPI")

# ─── Flask App Initialization ────────────────────────────────

app = Flask(__name__, static_folder="static")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

# ─── ProxyEngine Singleton ──────────────────────────────────

PROXY_ENGINE_INSTANCE = None

def _get_proxy_engine_ws():
    """Lazy-load the ProxyEngine singleton with WebSocket support."""
    global PROXY_ENGINE_INSTANCE
    if PROXY_ENGINE_INSTANCE is None:
        try:
            from proxy_engine import ProxyEngine
            PROXY_ENGINE_INSTANCE = ProxyEngine(ws_emit=_ws_emit)
            logger.info("🔌 ProxyEngine initialized with WebSocket support")
        except ImportError as e:
            logger.warning(f"ProxyEngine not available: {e}")
            return None
        except Exception as e:
            logger.error(f"ProxyEngine init error: {e}")
            return None
    return PROXY_ENGINE_INSTANCE


# ─── WebSocket Event Handlers ───────────────────────────────

def _ws_emit(event: str, data: dict):
    """Emit a WebSocket event to all connected clients."""
    try:
        socketio.emit(event, data)
    except Exception:
        pass


@socketio.on("connect")
def ws_connect():
    logger.info("🔌 WebSocket client connected")
    emit("connected", {"message": "Connected to Oracle Intelligence WebSocket"})


@socketio.on("disconnect")
def ws_disconnect():
    logger.info("🔌 WebSocket client disconnected")


@socketio.on("request_proxy_stats")
def ws_request_proxy_stats():
    """Client requests proxy stats via WebSocket."""
    engine = _get_proxy_engine_ws()
    if engine:
        emit("proxy_stats", engine.get_stats())
    else:
        emit("error", {"message": "ProxyEngine not available"})


@socketio.on("request_combo_stats")
def ws_request_combo_stats():
    """Client requests combo engine stats via WebSocket."""
    engine = _get_combo_engine()
    if engine:
        emit("combo_stats", engine.get_stats())
    else:
        emit("error", {"message": "ComboEngine not available"})


# ─── Proxy/WebSocket API Endpoints ────────────────────────

@app.route("/api/proxy/stats", methods=["GET"])
def api_proxy_stats():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    return jsonify({"success": True, "data": engine.get_stats()})


@app.route("/api/proxy/scrape", methods=["POST"])
def api_proxy_scrape():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    try:
        result = engine.scrape_proxies()
        result["sources_total"] = len(engine.scraper.SOURCES)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/proxy/test", methods=["POST"])
def api_proxy_test():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    try:
        stats = engine.test_proxies()
        return jsonify({"success": True, "data": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/proxy/mode", methods=["POST"])
def api_proxy_mode():
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "auto")
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    engine.mode = mode
    return jsonify({"success": True, "data": {"mode": mode}})


@app.route("/api/proxy/vpn", methods=["GET"])
def api_proxy_vpn():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    info = engine.detect_vpn()
    return jsonify({"success": True, "data": info})


@app.route("/api/proxy/add", methods=["POST"])
def api_proxy_add():
    data = request.get_json(silent=True) or {}
    text = data.get("proxies", "")
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    count = engine.pool.add_list(text, source="manual")
    return jsonify({"success": True, "data": {"added": count, "total": engine.pool.stats()["total"]}})


@app.route("/api/proxy/clear", methods=["POST"])
def api_proxy_clear():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    engine.pool.clear()
    return jsonify({"success": True, "data": {"message": "Pool cleared"}})


@app.route("/api/proxy/abort", methods=["POST"])
def api_proxy_abort():
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    engine.abort()
    return jsonify({"success": True, "data": {"message": "Aborted"}})


@app.route("/api/proxy/autopopulate", methods=["POST"])
def api_proxy_autopopulate():
    """
    Auto-poblar el pool de proxies: scrape + test en cadena.
    Ejecuta scrape de todas las fuentes y luego testea los proxies obtenidos.
    """
    engine = _get_proxy_engine_ws()
    if not engine:
        return jsonify({"success": False, "error": "ProxyEngine not available"}), 500
    try:
        start = time.time()

        # Paso 1: Scrape
        logger.info("🕸️ [AutoPopulate] Scraping proxies from all sources...")
        scrape_result = engine.scrape_proxies()
        scraped = scrape_result.get("total", 0)
        sources_count = len(scrape_result.get("by_source", {}))

        # Paso 2: Test (solo si hay proxies nuevos)
        pool_before = engine.pool.stats()
        untested_before = pool_before.get("untested", 0)

        if untested_before > 0:
            logger.info(f"🧪 [AutoPopulate] Testing {untested_before} proxies...")
            test_stats = engine.test_proxies()
        else:
            test_stats = {"message": "No new proxies to test"}

        elapsed = round(time.time() - start, 2)
        pool_after = engine.pool.stats()

        logger.info(f"✅ [AutoPopulate] Complete in {elapsed}s — {scraped} scraped, {pool_after.get('alive',0)} alive")

        return jsonify({
            "success": True,
            "data": {
                "scrape": {
                    "total_scraped": scraped,
                    "sources_count": sources_count,
                    "by_source": scrape_result.get("by_source", {}),
                },
                "test": {
                    "total_tested": untested_before,
                    "alive": pool_after.get("alive", 0),
                    "dead": pool_after.get("dead", 0),
                    "untested": pool_after.get("untested", 0),
                },
                "pool_after": pool_after,
                "took_seconds": elapsed,
            }
        })
    except Exception as e:
        logger.exception("AutoPopulate error")
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Combo Intelligence Endpoints ──────────────────────────

# Track server start time for uptime reporting
SERVER_START_TIME = time.time()

# Initialize the enhanced oracle engine
enhanced_engine = EnhancedOracleEngine()
base_engine = enhanced_engine.base_engine

# ─── Serve Static Files ──────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory("static", "index.html")

@app.route("/<path:path>")
def serve_static(path):
    if not path:
        return send_from_directory("static", "index.html")
    full_path = os.path.join("static", path)
    if os.path.exists(full_path):
        return send_from_directory("static", path)
    return jsonify({"success": False, "error": "Not found"}), 404


# ─── Core Search Endpoint ────────────────────────────────────

@app.route("/api/search", methods=["POST"])
def api_search():
    """
    Execute a search across OSINT dorking AND external APIs.
    
    Body: {
        "keyword": "comcast",
        "categories": ["logs","credentials"],
        "use_apis": true,
        "sample": true
    }
    """
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "").strip()
    
    if not keyword:
        return jsonify({"success": False, "error": "Keyword is required"}), 400
    
    categories = data.get("categories", None)
    use_apis = data.get("use_apis", True)
    use_sample = data.get("sample", True)
    
    try:
        result = enhanced_engine.search(
            keyword=keyword,
            use_apis=use_apis,
            categories=categories,
            sample=use_sample,
        )
        
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as e:
        logger.exception("Search error")
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Query Endpoint ──────────────────────────────────────────

@app.route("/api/query", methods=["POST"])
def api_query():
    """Query the indexed intelligence records with filters."""
    data = request.get_json(silent=True) or {}
    
    results = base_engine.query_index(
        keyword=data.get("keyword"),
        date_from=data.get("date_from"),
        date_to=data.get("date_to"),
        record_type=data.get("record_type"),
        severity=data.get("severity"),
        domain=data.get("domain"),
        page=data.get("page", 1),
        per_page=data.get("per_page", 50),
    )
    
    return jsonify({"success": True, "data": results})


# ─── ES-Powered Search Endpoint ────────────────────────────

@app.route("/api/es/search", methods=["POST"])
def api_es_search():
    """
    Full-text search across the Elasticsearch index.
    
    Body: {
        "query": "user@comcast.net",
        "keyword": "comcast",
        "record_type": "email:pass",
        "severity": "critical",
        "domain": "comcast.net",
        "date_from": "2023-01-01",
        "date_to": "2024-12-31",
        "page": 1,
        "per_page": 50
    }
    
    Returns: {
        "total", "results", "stats" (by_type, by_severity, by_domain),
        "took_ms", "using_elasticsearch"
    }
    """
    data = request.get_json(silent=True) or {}
    
    try:
        from elastic_index import get_index
        es_idx = get_index()
        from_ = (max(data.get("page", 1), 1) - 1) * min(data.get("per_page", 50), 200)
        
        result = es_idx.search(
            query_text=data.get("query", ""),
            keyword=data.get("keyword"),
            record_type=data.get("record_type"),
            severity=data.get("severity"),
            source_type=data.get("source_type"),
            domain=data.get("domain"),
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            from_=from_,
            size=min(data.get("per_page", 50), 200),
            include_stats=True,
        )
        
        return jsonify({
            "success": True,
            "data": {
                **result,
                "page": data.get("page", 1),
                "per_page": data.get("per_page", 50),
            }
        })
    except ImportError:
        return jsonify({"success": False, "error": "elastic_index module not available"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── ES Stats Endpoint ──────────────────────────────────────

@app.route("/api/es/stats", methods=["GET"])
def api_es_stats():
    """Get detailed stats from Elasticsearch aggregations."""
    try:
        from elastic_index import get_index
        es_idx = get_index()
        stats = es_idx.get_stats()
        return jsonify({"success": True, "data": stats})
    except ImportError:
        return jsonify({"success": False, "error": "elastic_index module not available"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Stats Endpoints ─────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Get overall system statistics."""
    stats = base_engine.get_index_stats()
    apis = []
    try:
        from intel_connectors import IntelOrchestrator
        orch = IntelOrchestrator()
        apis = orch.available_apis
    except:
        pass
    
    return jsonify({
        "success": True,
        "data": {
            **stats,
            "apis_configured": apis,
        }
    })


@app.route("/api/history", methods=["GET"])
def api_history():
    """Get search history."""
    return jsonify({"success": True, "data": base_engine.get_search_history()})


@app.route("/api/categories", methods=["GET"])
def api_categories():
    """Get available dork categories."""
    categories = list(base_engine.dork_templates.keys())
    descriptions = {
        "logs": "🔍 Logs y registros expuestos",
        "credentials": "🔑 Credenciales y contraseñas",
        "databases": "🗄️ Bases de datos expuestas",
        "config_files": "⚙️ Archivos de configuración",
        "paste_sites": "📋 Paste sites (Pastebin, etc.)",
        "exposed_directories": "📁 Directorios expuestos",
        "code_repos": "💻 Repositorios de código",
        "exploit_db": "💥 Bases de exploits",
    }
    return jsonify({
        "success": True,
        "data": [
            {"id": c, "name": c.replace("_", " ").title(), "description": descriptions.get(c, "")}
            for c in categories
        ]
    })


# ─── Deploy Status Endpoint ──────────────────────────────────

@app.route("/api/deploy/status", methods=["GET"])
def api_deploy_status():
    """
    Get full deployment health and status information.
    Used by the dashboard Deploy Status section.
    """
    uptime_seconds = time.time() - SERVER_START_TIME
    uptime_str = _format_uptime(uptime_seconds)
    
    # Platform detection (Render, Railway, Fly.io, etc.)
    is_railway = bool(os.environ.get("RAILWAY_SERVICE_ID"))
    is_render = bool(os.environ.get("RENDER"))
    is_fly = bool(os.environ.get("FLY_APP_NAME"))
    
    platform_info_detected = "render" if is_render else ("railway" if is_railway else ("fly" if is_fly else "local"))
    
    deploy_info = {
        "detected_platform": platform_info_detected,
        "railway": {
            "detected": is_railway,
            "service_name": os.environ.get("RAILWAY_SERVICE_NAME", "N/A"),
            "deployment_id": os.environ.get("RAILWAY_DEPLOYMENT_ID", "N/A"),
            "project_id": os.environ.get("RAILWAY_PROJECT_ID", "N/A"),
            "environment": os.environ.get("RAILWAY_ENVIRONMENT", "N/A"),
            "region": os.environ.get("RAILWAY_REGION", "N/A"),
            "public_url": os.environ.get("RAILWAY_PUBLIC_DOMAIN", "N/A"),
            "git_branch": os.environ.get("RAILWAY_GIT_BRANCH", "N/A"),
            "git_commit_sha": os.environ.get("RAILWAY_GIT_COMMIT_SHA", "N/A"),
            "service_id": os.environ.get("RAILWAY_SERVICE_ID", "N/A"),
        },
        "render": {
            "detected": is_render,
            "service_id": os.environ.get("RENDER_SERVICE_ID", "N/A"),
            "deploy_id": os.environ.get("RENDER_DEPLOY_ID", "N/A"),
            "service_name": os.environ.get("RENDER_SERVICE_NAME", "oraculo-inteligencia"),
            "region": os.environ.get("RENDER_REGION", "ohio"),
            "public_url": os.environ.get("RENDER_EXTERNAL_URL", "N/A"),
            "git_branch": os.environ.get("RENDER_GIT_BRANCH", os.environ.get("RAILWAY_GIT_BRANCH", "N/A")),
            "git_commit_sha": os.environ.get("RENDER_GIT_COMMIT", os.environ.get("RAILWAY_GIT_COMMIT_SHA", "N/A")),
        },
        "fly": {
            "detected": is_fly,
            "app_name": os.environ.get("FLY_APP_NAME", "N/A"),
            "region": os.environ.get("FLY_REGION", "N/A"),
            "public_url": os.environ.get("FLY_APP_HOSTNAME", "N/A"),
        },
        "generic": {
            "hostname": platform.node(),
            "port": os.environ.get("PORT", "8080"),
            "start_command": os.environ.get("RENDER_START_COMMAND", 
                          os.environ.get("RAILWAY_START_COMMAND", "gunicorn api:app")),
        },
    }
    
    # Memory info
    try:
        import psutil
        mem = psutil.Process().memory_info()
        mem_info = {
            "rss_mb": round(mem.rss / 1024 / 1024, 1),
            "vms_mb": round(mem.vms / 1024 / 1024, 1),
            "percent": psutil.Process().memory_percent(),
            "system_total_mb": round(psutil.virtual_memory().total / 1024 / 1024, 1),
            "system_available_mb": round(psutil.virtual_memory().available / 1024 / 1024, 1),
            "system_percent": psutil.virtual_memory().percent,
        }
    except ImportError:
        mem_info = {"rss_mb": "N/A", "vms_mb": "N/A", "note": "install psutil for details"}
    except Exception:
        mem_info = {"rss_mb": "N/A", "vms_mb": "N/A", "error": "permission denied"}
    
    # CPU / workers
    cpu_count = multiprocessing.cpu_count()
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=None)  # non-blocking, uses cached values
        load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
    except Exception:
        cpu_percent = 0
        load_avg = None
    
    # Gunicorn workers detection
    workers_count = _detect_workers_gunicorn()
    
    # Environment variables (which API keys are configured)
    env_vars = {
        "shodan": bool(get_shodan_key()),
        "hunter": bool(get_hunter_key()),
        "hibp": bool(get_hibp_key()),
        "virustotal": bool(get_vt_key()),
        "censys_token": bool(get_censys_token()),
        "es_hosts": bool(os.environ.get("ES_HOSTS")),
        "tor_proxy": os.environ.get("USE_TOR", "false"),
    }
    
    # Platform info
    platform_info = {
        "python_version": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "cpus": cpu_count,
    }
    
    # Health check results
    health = {
        "api_server": {"status": "passing", "uptime_seconds": round(uptime_seconds, 1), "uptime_str": uptime_str},
        "engine_initialized": bool(enhanced_engine is not None),
        "index_mode": "elasticsearch" if env_vars["es_hosts"] else "in_memory",
        "workers": workers_count,
        "memory": mem_info,
        "cpu_percent": cpu_percent,
    }
    
    # Test healthcheck latency
    healthcheck_latency = _measure_healthcheck_latency()
    
    return jsonify({
        "success": True,
        "data": {
            "platform": platform_info,
            "deploy": deploy_info,
            "health": health,
            "healthcheck_latency_ms": healthcheck_latency,
            "env_vars": env_vars,
            "server_time": datetime.now().isoformat(),
            "started_at": datetime.fromtimestamp(SERVER_START_TIME).isoformat(),
            "active_requests": 0,  # gunicorn manages this externally
        }
    })


def _format_uptime(seconds: float) -> str:
    """Format uptime seconds into human-readable string."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m {secs}s"
    elif hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def _detect_workers_gunicorn() -> dict:
    """Detect gunicorn workers using environment variables (portable, no subprocess)."""
    worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "sync")
    is_gunicorn = "gunicorn" in os.environ.get("SERVER_SOFTWARE", "").lower()
    max_config = int(os.environ.get("GUNICORN_WORKERS", "2"))
    
    # In gunicorn, each worker process has a distinct PID.
    # We can detect the current role from env vars gunicorn sets.
    # For a reliable count, gunicorn's --workers flag is our best bet.
    if is_gunicorn:
        worker_count = max_config  # best estimate from config
    else:
        worker_count = "N/A (dev mode)"
    
    return {
        "is_gunicorn": is_gunicorn,
        "worker_count": worker_count,
        "worker_class": worker_class,
        "max_workers": max_config,
    }


def _measure_healthcheck_latency() -> dict:
    """Measure latency for key health check operations."""
    results = {}
    
    # Simple stats endpoint latency
    start = time.perf_counter()
    _ = base_engine.get_index_stats()
    results["stats_endpoint_ms"] = round((time.perf_counter() - start) * 1000, 1)
    
    # Database/index latency
    start = time.perf_counter()
    _ = base_engine.query_index(page=1, per_page=1)
    results["query_index_ms"] = round((time.perf_counter() - start) * 1000, 1)
    
    return results


# ─── External API Status ─────────────────────────────────────

@app.route("/api/apis/status", methods=["GET"])
def api_apis_status():
    """Check which external APIs are configured and available."""
    try:
        from intel_connectors import IntelOrchestrator
        orch = IntelOrchestrator()
        configured = orch.available_apis
        return jsonify({
            "success": True,
            "data": {
                "configured_apis": configured,
                "total": len(configured),
                "all_apis": ["shodan", "hunter", "hibp", "virustotal", "censys"],
                "configured": {api: api in configured for api in 
                              ["shodan", "hunter", "hibp", "virustotal", "censys"]},
                "env_vars": {
                    "shodan": "SHODAN_API_KEY",
                    "hunter": "HUNTER_API_KEY",
                    "hibp": "HIBP_API_KEY",
                    "virustotal": "VT_API_KEY",
                    "censys": "CENSYS_TOKEN or CENSYS_API_ID + SECRET",
                }
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ─── Shodan Endpoints ────────────────────────────────────────

@app.route("/api/shodan/search", methods=["POST"])
def api_shodan_search():
    """Search Shodan for exposed services."""
    try:
        from intel_connectors import ShodanConnector
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        limit = data.get("limit", 20)
        
        if not query:
            return jsonify({"success": False, "error": "Query is required"}), 400
        
        connector = ShodanConnector()
        result = connector.search(query, limit=limit)
        return jsonify({"success": result["success"], "data": result})
    except ImportError:
        return jsonify({"success": False, "error": "intel_connectors module not available"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/shodan/host", methods=["POST"])
def api_shodan_host():
    """Get Shodan details for a specific IP."""
    try:
        from intel_connectors import ShodanConnector
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "").strip()
        if not ip:
            return jsonify({"success": False, "error": "IP is required"}), 400
        connector = ShodanConnector()
        result = connector.host(ip)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Hunter.io Endpoints ─────────────────────────────────────

@app.route("/api/hunter/domain", methods=["POST"])
def api_hunter_domain():
    """Discover email addresses for a domain via Hunter.io."""
    try:
        from intel_connectors import HunterConnector
        data = request.get_json(silent=True) or {}
        domain = data.get("domain", "").strip()
        limit = data.get("limit", 25)
        if not domain:
            return jsonify({"success": False, "error": "Domain is required"}), 400
        connector = HunterConnector()
        result = connector.domain_search(domain, limit=limit)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/hunter/verify", methods=["POST"])
def api_hunter_verify():
    """Verify an email address via Hunter.io."""
    try:
        from intel_connectors import HunterConnector
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
        connector = HunterConnector()
        result = connector.verify_email(email)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── HaveIBeenPwned Endpoints ────────────────────────────────

@app.route("/api/hibp/email", methods=["POST"])
def api_hibp_email():
    """Check if an email appears in known breaches via HIBP."""
    try:
        from intel_connectors import HIBPConnector
        data = request.get_json(silent=True) or {}
        email = data.get("email", "").strip()
        if not email:
            return jsonify({"success": False, "error": "Email is required"}), 400
        connector = HIBPConnector()
        result = connector.check_email(email)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/hibp/domain", methods=["POST"])
def api_hibp_domain():
    """Check all breaches for a domain via HIBP."""
    try:
        from intel_connectors import HIBPConnector
        data = request.get_json(silent=True) or {}
        domain = data.get("domain", "").strip()
        if not domain:
            return jsonify({"success": False, "error": "Domain is required"}), 400
        connector = HIBPConnector()
        result = connector.check_domain(domain)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── VirusTotal Endpoints ────────────────────────────────────

@app.route("/api/vt/domain", methods=["POST"])
def api_vt_domain():
    """Get VirusTotal threat report for a domain."""
    try:
        from intel_connectors import VirusTotalConnector
        data = request.get_json(silent=True) or {}
        domain = data.get("domain", "").strip()
        if not domain:
            return jsonify({"success": False, "error": "Domain is required"}), 400
        connector = VirusTotalConnector()
        result = connector.analyze_domain(domain)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/vt/ip", methods=["POST"])
def api_vt_ip():
    """Get VirusTotal threat report for an IP address."""
    try:
        from intel_connectors import VirusTotalConnector
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "").strip()
        if not ip:
            return jsonify({"success": False, "error": "IP is required"}), 400
        connector = VirusTotalConnector()
        result = connector.analyze_ip(ip)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Censys Endpoints ────────────────────────────────────────

@app.route("/api/censys/search", methods=["POST"])
def api_censys_search():
    """Search Censys for hosts matching a query."""
    try:
        from intel_connectors import CensysConnector
        data = request.get_json(silent=True) or {}
        query = data.get("query", "").strip()
        limit = data.get("limit", 20)
        if not query:
            return jsonify({"success": False, "error": "Query is required"}), 400
        connector = CensysConnector()
        result = connector.search_hosts(query, limit=limit)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/censys/host", methods=["POST"])
def api_censys_host():
    """Get Censys details for a specific host/IP."""
    try:
        from intel_connectors import CensysConnector
        data = request.get_json(silent=True) or {}
        ip = data.get("ip", "").strip()
        if not ip:
            return jsonify({"success": False, "error": "IP is required"}), 400
        connector = CensysConnector()
        result = connector.view_host(ip)
        return jsonify({"success": result["success"], "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Combo Intelligence Endpoints ──────────────────────────

COMBO_ENGINE = None

def _get_combo_engine():
    """Lazy-load the ComboLeecherEngine singleton."""
    global COMBO_ENGINE
    if COMBO_ENGINE is None:
        try:
            from combo_leecher_engine import ComboLeecherEngine
            COMBO_ENGINE = ComboLeecherEngine(oracle_engine=base_engine)
            logger.info("🔐 Combo Intelligence Engine initialized")
        except Exception as e:
            logger.error(f"Combo engine init error: {e}")
            return None
    return COMBO_ENGINE


@app.route("/api/combo/leech", methods=["POST"])
def api_combo_leech():
    """
    Execute a combo leech operation — scrape, parse, validate, index.
    
    Body: {
        "keyword": "comcast",
        "sources": ["paste", "telegram", "dorking"],
        "validate": false,
        "max_per_source": 20
    }
    """
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "").strip()
    
    if not keyword:
        return jsonify({"success": False, "error": "Keyword is required"}), 400
    
    engine = _get_combo_engine()
    if not engine:
        return jsonify({"success": False, "error": "Combo engine not available"}), 500
    
    sources = data.get("sources", ["paste", "telegram", "dorking"])
    validate = data.get("validate", False)
    max_per_source = data.get("max_per_source", 20)
    
    try:
        result = engine.leech(
            keyword=keyword,
            sources=sources,
            validate=validate,
            max_per_source=max_per_source,
        )
        return jsonify({
            "success": True,
            "data": result.to_dict(),
        })
    except Exception as e:
        logger.exception("Combo leech error")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/combo/stats", methods=["GET"])
def api_combo_stats():
    """Get combo intelligence engine statistics."""
    engine = _get_combo_engine()
    if not engine:
        return jsonify({"success": False, "error": "Combo engine not available"}), 500
    return jsonify({"success": True, "data": engine.get_stats()})


@app.route("/api/combo/export/<fmt>", methods=["GET"])
def api_combo_export(fmt: str):
    """Export indexed combos in various formats."""
    engine = _get_combo_engine()
    if not engine:
        return jsonify({"success": False, "error": "Combo engine not available"}), 500
    
    keyword = request.args.get("keyword", None)
    fmt = fmt.lower()
    
    if fmt == "txt":
        content = engine.export_txt(keyword)
        mimetype = "text/plain"
        filename = f"combos_{keyword or 'all'}.txt"
    elif fmt == "csv":
        content = engine.export_csv(keyword)
        mimetype = "text/csv"
        filename = f"combos_{keyword or 'all'}.csv"
    elif fmt == "json":
        content = engine.export_json(keyword)
        mimetype = "application/json"
        filename = f"combos_{keyword or 'all'}.json"
    else:
        return jsonify({"success": False, "error": f"Unknown format: {fmt}"}), 400
    
    response = app.response_class(
        response=content,
        status=200,
        mimetype=mimetype,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
    return response


@app.route("/api/combo/validate", methods=["POST"])
def api_combo_validate():
    """Validate a single combo via SMTP."""
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password required"}), 400
    
    engine = _get_combo_engine()
    if not engine:
        return jsonify({"success": False, "error": "Combo engine not available"}), 500
    
    try:
        result = engine.validator.validate_smtp(email, password)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Chat Endpoint ───────────────────────────────────────────

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """AI-powered chat endpoint for the Oracle Assistant."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    context = data.get("context", {})
    
    if not message:
        return jsonify({"success": False, "error": "Message is required"}), 400
    
    response = _generate_chat_response(message, context)
    
    return jsonify({
        "success": True,
        "data": {
            "response": response,
            "timestamp": datetime.now().isoformat(),
        }
    })


def _generate_chat_response(message: str, context: dict) -> str:
    """Generate a contextual response for the chat assistant."""
    msg_lower = message.lower()
    stats = base_engine.get_index_stats()
    
    # API status
    if "api" in msg_lower and ("status" in msg_lower or "configuradas" in msg_lower or "disponibles" in msg_lower):
        apis_status = []
        try:
            from intel_connectors import IntelOrchestrator
            orch = IntelOrchestrator()
            if orch.shodan.enabled: apis_status.append("🔍 Shodan")
            if orch.hunter.enabled: apis_status.append("📧 Hunter.io")
            if orch.hibp.enabled: apis_status.append("🔒 HaveIBeenPwned")
            if orch.virustotal.enabled: apis_status.append("🦠 VirusTotal")
            if orch.censys.enabled: apis_status.append("🌐 Censys")
        except:
            pass
        
        if apis_status:
            return "🔌 **APIs de inteligencia configuradas:**\n\n" + "\n".join(f"• {api}" for api in apis_status) + \
                   "\n\n_Nota: Las APIs no configuradas simplemente se omiten sin errores._"
        else:
            return "🔌 **No hay APIs de inteligencia configuradas.**\n\nPara activarlas, configura las variables de entorno:\n" + \
                   "• `SHODAN_API_KEY` — Shodan\n" + \
                   "• `HUNTER_API_KEY` — Hunter.io\n" + \
                   "• `HIBP_API_KEY` — HaveIBeenPwned\n" + \
                   "• `VT_API_KEY` — VirusTotal\n" + \
                   "• `CENSYS_TOKEN` — Censys"
    
    # Keyword search command
    if msg_lower.startswith("/buscar ") or msg_lower.startswith("buscar "):
        keyword = msg_lower.replace("/buscar ", "").replace("buscar ", "").strip()
        if keyword:
            return f"🔍 Iniciando búsqueda multi-fuente para **'{keyword}'**... Se consultarán todas las APIs disponibles además del dorking OSINT."
    
    # Stats query
    if "cuantos" in msg_lower and "registro" in msg_lower:
        return f"📊 Total en índice: **{stats['total_records']}** registros en **{stats['total_keywords']}** búsquedas."
    
    # Help
    if "ayuda" in msg_lower or "comandos" in msg_lower or "qué puedes" in msg_lower:
        return (
            "🤖 **Comandos disponibles:**\n\n"
            "🔍 `buscar <keyword>` — Búsqueda multi-fuente\n"
            "📊 `¿Cuántos registros?` — Estadísticas\n"
            "🔌 `APIs disponibles` — Estado de conectores\n"
            "📋 `resumen` — Resumen completo\n"
            "❓ `ayuda` — Esta ayuda\n\n"
            "_Las APIs externas se consultan automáticamente si están configuradas._"
        )
    
    # Summary
    if "resumen" in msg_lower or "general" in msg_lower:
        apis_count = 0
        try:
            from intel_connectors import IntelOrchestrator
            apis_count = len(IntelOrchestrator().available_apis)
        except:
            pass
        
        return (
            "📋 **RESUMEN DEL ORÁCULO**\n\n"
            f"📊 Registros indexados: **{stats['total_records']}**\n"
            f"🔑 Palabras clave: **{stats['total_keywords']}**\n"
            f"🔄 Búsquedas: **{stats['total_searches']}**\n"
            f"🔌 APIs externas: **{apis_count}/5** configuradas\n\n"
            "_Realiza una búsqueda para activar todas las fuentes._"
        )
    
    # Default
    return (
        "🤔 No entendí tu pregunta. Prueba con:\n\n"
        "• `buscar comcast` — Búsqueda multi-fuente\n"
        "• `APIs disponibles` — Estado de conectores\n"
        "• `¿Cuántos registros?` — Estadísticas\n"
        "• `resumen` — Panorama general\n"
        "• `ayuda` — Todos los comandos"
    )


# ─── Ping/Uptime Endpoint (ultraligero para monitoreo) ─────

@app.route("/api/ping", methods=["GET"])
def api_ping():
    """
    Endpoint ultraligero para UptimeRobot/monitoring.
    Responde en <5ms — sin psutil, sin DB, sin Engine.
    """
    uptime_seconds = round(time.time() - SERVER_START_TIME, 1)
    return jsonify({
        "success": True,
        "data": {
            "status": "ok",
            "service": "oraculo-inteligencia",
            "version": "2.0",
            "uptime_seconds": uptime_seconds,
            "uptime_str": _format_uptime(uptime_seconds),
            "server_time": datetime.now().isoformat(),
            "platform": "render" if os.environ.get("RENDER") else "local",
            "ping_interval": "5-10 minutes recommended for UptimeRobot",
        }
    })


# ─── Dump Finder Endpoint ────────────────────────────

DUMP_FINDER_INSTANCE = None

def _get_dump_finder():
    """Lazy-load the DumpFinder singleton."""
    global DUMP_FINDER_INSTANCE
    if DUMP_FINDER_INSTANCE is None:
        try:
            DUMP_FINDER_INSTANCE = DumpFinder()
            logger.info("🛡️ DumpFinder initialized")
        except Exception as e:
            logger.error(f"DumpFinder init error: {e}")
            return None
    return DUMP_FINDER_INSTANCE


@app.route("/api/dump/search", methods=["POST"])
def api_dump_search():
    """
    Execute a Dump Finder search — busca URLs con dumps de credenciales,
    extrae email:pass, filtra por fecha, guarda en disco.

    Body: {
        "keyword": "comcast",
        "year": 2023,
        "month": null,
        "date_from": null,
        "date_to": null,
        "max_dorks": 15,
        "max_fetches": 10,
        "save_to_disk": true
    }
    """
    data = request.get_json(silent=True) or {}
    keyword = data.get("keyword", "").strip()

    if not keyword:
        return jsonify({"success": False, "error": "Keyword is required"}), 400

    finder = _get_dump_finder()
    if not finder:
        return jsonify({"success": False, "error": "DumpFinder not available"}), 500

    try:
        result = finder.search(
            keyword=keyword,
            year=data.get("year"),
            month=data.get("month"),
            date_from=data.get("date_from"),
            date_to=data.get("date_to"),
            max_dorks=data.get("max_dorks", 15),
            max_fetches=data.get("max_fetches", 10),
            save_to_disk=data.get("save_to_disk", True),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        logger.exception("Dump search error")
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "").lower() in ("true", "1", "yes")
    
    logger.info("🚀 Oracle Intelligence API v2.0 starting on port %d", port)
    logger.info("📡 External API connectors available via IntelOrchestrator")
    logger.info("📊 Deploy status endpoint at /api/deploy/status")
    
    # Use socketio.run for WebSocket support
    logger.info("🔌 WebSocket support available at /socket.io/")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug)
