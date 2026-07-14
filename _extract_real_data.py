"""
╔══════════════════════════════════════════════════════════════╗
║  EXTRACCIÓN MASIVA DE DATOS REALES                          ║
║  Hunter.io · VirusTotal · Censys · Shodan                   ║
║  Múltiples dominios del sector telecomunicaciones           ║
╚══════════════════════════════════════════════════════════════╝
"""
import json
import time
import datetime
import requests
import sys
import os

API_BASE = "https://oraculo-inteligencia.onrender.com"

DOMAINS = [
    # Telecomunicaciones / ISP
    "comcast.com", "xfinity.com", "verizon.com", "att.com",
    "sbcglobal.net", "centurylink.com", "spectrum.com",
    # Tecnología
    "microsoft.com", "google.com", "apple.com",
    # Redes sociales
    "facebook.com", "linkedin.com",
]

def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def call_api(endpoint: str, payload: dict, name: str) -> dict:
    """Call a deployed API endpoint with retry logic."""
    url = f"{API_BASE}{endpoint}"
    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                print(f"  ⏳ Rate limited, waiting 30s...")
                time.sleep(30)
                continue
            else:
                return {"success": False, "error": f"HTTP {resp.status_code}"}
        except requests.exceptions.Timeout:
            print(f"  ⏳ Timeout, retrying ({attempt+1}/3)...")
            time.sleep(5)
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "Max retries exceeded"}

# ─── Result storage ───
results = {
    "hunter": {},
    "virustotal": {},
    "censys": {},
    "shodan": {},
}

print("=" * 72)
print("  🛸  EXTRACCIÓN MASIVA DE DATOS REALES")
print(f"  Iniciado: {ts()}")
print(f"  API: {API_BASE}")
print(f"  Dominios: {len(DOMAINS)}")
print("=" * 72)

# ─── FASE 1: Hunter.io ───
print("\n📧  FASE 1: HUNTER.IO — Descubrimiento de emails")
print("-" * 50)

for i, domain in enumerate(DOMAINS, 1):
    print(f"  [{i}/{len(DOMAINS)}] {domain}...", end=" ", flush=True)
    result = call_api("/api/hunter/domain", {"domain": domain, "limit": 10}, "hunter")
    
    if result.get("success"):
        data = result.get("data", {})
        emails = data.get("emails", [])
        total = data.get("total", 0)
        results["hunter"][domain] = {"total": total, "emails": emails}
        print(f"✅ {total} emails")
        for e in emails[:3]:
            print(f"     📧 {e.get('value','?'):<40} conf:{e.get('confidence',0)}%")
    else:
        results["hunter"][domain] = {"total": 0, "emails": [], "error": result.get("data",{}).get("error","")}
        print(f"❌ {result.get('data',{}).get('error','error')}")
    
    time.sleep(2)  # Rate limit

# ─── FASE 2: VirusTotal ───
print("\n🦠  FASE 2: VIRUSTOTAL — Análisis de amenazas")
print("-" * 50)

for i, domain in enumerate(DOMAINS, 1):
    print(f"  [{i}/{len(DOMAINS)}] {domain}...", end=" ", flush=True)
    result = call_api("/api/vt/domain", {"domain": domain}, "virustotal")
    
    if result.get("success"):
        data = result.get("data", {})
        results["virustotal"][domain] = {
            "malicious": data.get("malicious", 0),
            "suspicious": data.get("suspicious", 0),
            "harmless": data.get("harmless", 0),
            "reputation": data.get("reputation", 0),
            "categories": data.get("categories", []),
        }
        m = data.get("malicious", 0)
        s = data.get("suspicious", 0)
        h = data.get("harmless", 0)
        rep = data.get("reputation", 0)
        cats = ", ".join(data.get("categories", [])[:3])
        print(f"✅ mal:{m} sus:{s} ok:{h} rep:{rep} [{cats}]")
    else:
        results["virustotal"][domain] = {"error": result.get("error", "unknown")}
        print(f"❌ {result.get('data',{}).get('error',result.get('error','error'))}")
    
    time.sleep(15)  # VT free: 4/min → 15s between calls

# ─── FASE 3: Censys ───
print("\n🌐  FASE 3: CENSYS — Dispositivos expuestos")
print("-" * 50)

for i, domain in enumerate(DOMAINS[:5], 1):  # Only first 5 for Censys
    print(f"  [{i}/5] {domain}...", end=" ", flush=True)
    result = call_api("/api/censys/search", {"query": domain, "limit": 5}, "censys")
    
    if result.get("success"):
        data = result.get("data", {})
        hosts = data.get("results", [])
        total = data.get("total", 0)
        results["censys"][domain] = {"total": total, "hosts": hosts}
        print(f"✅ {total} hosts encontrados")
        for h in hosts[:2]:
            ip = h.get("ip", "?")
            services = [s.get("service_name","?") for s in h.get("services",[])]
            print(f"     🌐 {ip:<16} servicios: {', '.join(services[:3])}")
    else:
        results["censys"][domain] = {"error": result.get("data",{}).get("error","")}
        print(f"❌ {result.get('data',{}).get('error','error')}")
    
    time.sleep(2)

# ─── GUARDAR ARCHIVOS ───
print("\n💾  GUARDANDO RESULTADOS...")
print("-" * 50)

ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

# 1. Reporte completo
report_file = f"datos_reales_completos_{ts_str}.txt"
with open(report_file, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write("  🛸  ORÁCULO DE INTELIGENCIA — EXTRACCIÓN DE DATOS REALES\n")
    f.write(f"  Fecha: {ts()}\n")
    f.write(f"  API: {API_BASE}\n")
    f.write("=" * 80 + "\n\n")

    # Hunter
    f.write("╔══════════════════════════════════════════════════════════════╗\n")
    f.write("║  📧 HUNTER.IO — EMAILS REALES POR DOMINIO                  ║\n")
    f.write("╚══════════════════════════════════════════════════════════════╝\n\n")
    for domain, data in results["hunter"].items():
        f.write(f"  {domain} — {data.get('total', 0)} emails\n")
        for e in data.get("emails", []):
            f.write(f"    📧 {e.get('value','?'):<45} conf:{e.get('confidence',0)}%  ")
            f.write(f"tipo:{e.get('type','?')}  cargo:{e.get('position','?')}\n")
            for s in e.get("sources", [])[:2]:
                f.write(f"       fuente: {s.get('uri','?')}\n")
        f.write("\n")

    # VirusTotal
    f.write("╔══════════════════════════════════════════════════════════════╗\n")
    f.write("║  🦠 VIRUSTOTAL — ANÁLISIS DE AMENAZAS                      ║\n")
    f.write("╚══════════════════════════════════════════════════════════════╝\n\n")
    for domain, data in results["virustotal"].items():
        if "error" in data:
            f.write(f"  {domain} — ERROR: {data['error']}\n\n")
        else:
            f.write(f"  {domain}\n")
            f.write(f"    Maliciosos:  {data.get('malicious', 0)}\n")
            f.write(f"    Sospechosos: {data.get('suspicious', 0)}\n")
            f.write(f"    Limpios:     {data.get('harmless', 0)}\n")
            f.write(f"    Reputación:  {data.get('reputation', 0)}\n")
            if data.get("categories"):
                f.write(f"    Categorías:  {', '.join(data['categories'][:5])}\n")
            f.write("\n")

    # Censys
    f.write("╔══════════════════════════════════════════════════════════════╗\n")
    f.write("║  🌐 CENSYS — DISPOSITIVOS EXPUESTOS                        ║\n")
    f.write("╚══════════════════════════════════════════════════════════════╝\n\n")
    for domain, data in results["censys"].items():
        f.write(f"  {domain} — {data.get('total', 0)} hosts\n")
        for h in data.get("hosts", []):
            ip = h.get("ip", "?")
            services = [f"{s.get('service_name','?')}/{s.get('port','?')}" for s in h.get("services",[])]
            loc = h.get("location", {})
            country = loc.get("country", "?")
            f.write(f"    🌐 {ip:<16} {', '.join(services[:4]):<40} {country}\n")
        f.write("\n")

    # Resumen
    f.write("=" * 80 + "\n")
    f.write("  📊 RESUMEN GENERAL\n")
    f.write("=" * 80 + "\n\n")
    
    total_emails = sum(d.get("total",0) for d in results["hunter"].values())
    domains_with_emails = sum(1 for d in results["hunter"].values() if d.get("total",0) > 0)
    total_malicious = sum(d.get("malicious",0) for d in results["virustotal"].values() if "malicious" in d)
    total_hosts = sum(d.get("total",0) for d in results["censys"].values())
    
    f.write(f"  📧 Emails descubiertos:  {total_emails} en {domains_with_emails} dominios\n")
    f.write(f"  🦠 Dominios maliciosos:  {total_malicious} detecciones\n")
    f.write(f"  🌐 Hosts en Censys:     {total_hosts}\n")
    f.write(f"\n  🕐 Extracción completada: {ts()}\n")

# 2. Solo emails (formato CSV)
emails_file = f"emails_reales_{ts_str}.csv"
with open(emails_file, "w", encoding="utf-8") as f:
    f.write("email,dominio,confianza,tipo,cargo\n")
    for domain, data in results["hunter"].items():
        for e in data.get("emails", []):
            f.write(f"{e.get('value','')},{domain},{e.get('confidence',0)},{e.get('type','')},{e.get('position','')}\n")

# 3. Solo amenazas (formato JSON)
threats_file = f"amenazas_reales_{ts_str}.json"
with open(threats_file, "w", encoding="utf-8") as f:
    json.dump(results["virustotal"], f, indent=2, ensure_ascii=False)

# ─── MOSTRAR RESUMEN ───
print("\n" + "=" * 72)
print("  📊  RESUMEN FINAL DE EXTRACCIÓN")
print("=" * 72)

total_emails = sum(d.get("total",0) for d in results["hunter"].values())
domains_with_emails = sum(1 for d in results["hunter"].values() if d.get("total",0) > 0)
total_malicious = sum(d.get("malicious",0) for d in results["virustotal"].values() if "malicious" in d)
malicious_domains = [d for d, v in results["virustotal"].items() if isinstance(v, dict) and v.get("malicious", 0) > 0]
total_hosts = sum(d.get("total",0) for d in results["censys"].values())

print(f"\n  📧  Hunter.io — Emails reales:")
print(f"       {total_emails} emails descubiertos en {domains_with_emails} dominios")
for domain, data in sorted(results["hunter"].items(), key=lambda x: -x[1].get("total",0)):
    if data.get("total", 0) > 0:
        emails_preview = [e.get("value","") for e in data.get("emails",[])[:3]]
        print(f"       {domain}: {data['total']} emails — {', '.join(emails_preview)}")

print(f"\n  🦠  VirusTotal — Amenazas:")
print(f"       {total_malicious} detecciones maliciosas")
if malicious_domains:
    print(f"       Dominios con malware: {', '.join(malicious_domains)}")

print(f"\n  🌐  Censys — Dispositivos:")
print(f"       {total_hosts} hosts expuestos encontrados")

print(f"\n  📁  Archivos guardados:")
print(f"       📄 {report_file} — Reporte completo")
print(f"       📄 {emails_file} — Emails CSV")
print(f"       📄 {threats_file} — Amenazas JSON")

print("\n" + "=" * 72)
print(f"  ✅  EXTRACCIÓN COMPLETADA: {ts()}")
print("=" * 72)
