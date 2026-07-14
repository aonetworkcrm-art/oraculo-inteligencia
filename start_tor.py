"""
╔══════════════════════════════════════════════════════════════╗
║  TOR LAUNCHER — Inicia Tor y ejecuta el DumpFinder         ║
║                                                             ║
║  Uso:                                                       ║
║    python start_tor.py                      # Solo Tor     ║
║    python start_tor.py --dump comcast       # Tor + Dump    ║
║    python start_tor.py --stop               # Mata Tor      ║
╚══════════════════════════════════════════════════════════════╝
"""
import os
import sys
import time
import subprocess
import signal
import requests
from pathlib import Path

# ─── CONFIG ───
TOR_EXE = str(Path.home() / "tor_browser" / "tor" / "tor" / "tor.exe")
TOR_DATA = str(Path.home() / "tor_browser" / "tor_data")
TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051
TOR_PROXY = f"socks5h://127.0.0.1:{TOR_SOCKS_PORT}"

os.makedirs(TOR_DATA, exist_ok=True)

def is_tor_running():
    """Check if Tor SOCKS proxy is responding."""
    try:
        r = requests.get(
            "https://check.torproject.org/",
            proxies={"http": TOR_PROXY, "https": TOR_PROXY},
            timeout=5
        )
        return "Congratulations" in r.text
    except:
        return False

def get_tor_ip():
    """Get current Tor exit node IP."""
    try:
        r = requests.get(
            "https://httpbin.org/ip",
            proxies={"http": TOR_PROXY, "https": TOR_PROXY},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("origin", "unknown")
    except:
        pass
    return "unknown"

def start_tor():
    """Start Tor daemon and wait for it to connect."""
    if is_tor_running():
        ip = get_tor_ip()
        print(f"✅ Tor ya está corriendo (IP: {ip})")
        return True

    if not os.path.exists(TOR_EXE):
        print(f"❌ Tor no encontrado en: {TOR_EXE}")
        print("   Descarga Tor Expert Bundle desde:")
        print("   https://www.torproject.org/download/tor/")
        return False

    print(f"🚀 Iniciando Tor desde: {TOR_EXE}")
    print(f"   Proxy SOCKS5: {TOR_PROXY}")
    print(f"   Data dir: {TOR_DATA}")

    # Build command — Windows friendly args
    cmd = [
        TOR_EXE,
        f"--SOCKSPort", str(TOR_SOCKS_PORT),
        f"--ControlPort", str(TOR_CONTROL_PORT),
        f"--DataDirectory", TOR_DATA,
        "--Log", f"notice file {TOR_DATA}/tor.log",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception as e:
        print(f"❌ Error iniciando Tor: {e}")
        return False

    # Wait for Tor to connect (up to 60s)
    print("   ⏳ Esperando que Tor conecte...")
    for i in range(30):
        time.sleep(2)
        if is_tor_running():
            ip = get_tor_ip()
            print(f"✅ Tor conectado! (IP: {ip}, tomó { (i+1)*2 }s)")
            # Save PID
            with open(os.path.join(TOR_DATA, "tor.pid"), "w") as f:
                f.write(str(proc.pid))
            return True
        if i % 5 == 0 and i > 0:
            print(f"   Aún esperando... ({i*2}s)")

    print("❌ Tor no conectó después de 60s")
    print("   Revisa: firewall, bloqueos de red, o logs en:")
    print(f"   {TOR_DATA}/tor.log")
    return False

def stop_tor():
    """Stop Tor daemon."""
    pid_file = os.path.join(TOR_DATA, "tor.pid")
    if os.path.exists(pid_file):
        with open(pid_file) as f:
            pid = int(f.read().strip())
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            print(f"🛑 Tor detenido (PID: {pid})")
            os.remove(pid_file)
        except Exception as e:
            print(f"⚠️ Error deteniendo Tor: {e}")
    else:
        print("ℹ️ Tor no está corriendo (no hay PID file)")

def run_dumpfinder(keyword):
    """Run DumpFinder with Tor proxy enabled."""
    print(f"\n🔍 Ejecutando DumpFinder para: {keyword}")
    print(f"   Via Tor: {TOR_PROXY}")
    print("=" * 50)

    env = os.environ.copy()
    env["TOR_PROXY"] = TOR_PROXY
    # Route ALL requests through Tor (HTTP_PROXY + HTTPS_PROXY)
    env["HTTP_PROXY"] = TOR_PROXY
    env["HTTPS_PROXY"] = TOR_PROXY
    env["REQUESTS_CA_BUNDLE"] = ""

    # Change to oraculo-inteligencia directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    cmd = [sys.executable, "dump_finder.py", keyword]
    proc = subprocess.Popen(cmd, env=env)
    proc.wait()

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Tor Launcher para DumpFinder")
    parser.add_argument("--stop", action="store_true", help="Detener Tor")
    parser.add_argument("--dump", type=str, default=None,
                        help="Keyword para DumpFinder (ej: comcast)")
    parser.add_argument("--status", action="store_true", help="Ver estado de Tor")
    args = parser.parse_args()

    if args.stop:
        stop_tor()
        return

    if args.status:
        if is_tor_running():
            ip = get_tor_ip()
            print(f"✅ Tor ACTIVO — IP: {ip}")
        else:
            print("❌ Tor NO está corriendo")
        return

    # Start Tor
    ok = start_tor()
    if not ok:
        sys.exit(1)

    # Show IP
    time.sleep(1)
    ip = get_tor_ip()
    print(f"\n🌍 IP actual (Tor): {ip}")
    print(f"   Proxy: {TOR_PROXY}")

    # Run DumpFinder if keyword provided
    if args.dump:
        run_dumpfinder(args.dump)
    else:
        print("\n💡 Tip: Agrega --dump comcast para buscar con Tor")
        print("   Ej: python start_tor.py --dump comcast")

if __name__ == "__main__":
    main()
