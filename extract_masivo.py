"""
╔══════════════════════════════════════════════════════════════╗
║  EXTRACCIÓN MASIVA — APIs Reales (Hunter·VT·Shodan·Censys) ║
║  Ejecución LOCAL para evitar bloqueos de Render             ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys, os, json, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intel_connectors import IntelOrchestrator

DOMAINS = [
    "comcast.com", "xfinity.com", "verizon.com", "att.com",
    "microsoft.com", "google.com", "apple.com",
    "facebook.com", "linkedin.com", "sbcglobal.net",
]

def main():
    orchestrator = IntelOrchestrator()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ALL = {}

    print("=" * 70)
    print("  🛸  EXTRACCIÓN MASIVA CON APIs REALES")
    print(f"  Inicio: {datetime.now().isoformat()}")
    print(f"  APIs: {orchestrator.available_apis}")
    print(f"  Dominios: {len(DOMAINS)}")
    print("=" * 70)

    for i, domain in enumerate(DOMAINS, 1):
        print(f"\n[{i}/{len(DOMAINS)}] 🔍 {domain}")
        print("-" * 50)

        result = orchestrator.investigate_keyword(domain)
        ALL[domain] = result

        # Hunter
        hr = result.get("results", {}).get("hunter", {})
        if hr.get("success") and hr.get("emails"):
            emails = hr["emails"]
            print(f"  📧 Hunter: {len(emails)} emails")
            for e in emails[:5]:
                pos = e.get("position", "") or ""
                print(f"     {e['value']:<40} conf:{e['confidence']}%  {pos[:25]}")

        # VirusTotal
        vt = result.get("results", {}).get("virustotal", {})
        if vt.get("success"):
            print(f"  🦠 VT: {vt.get('malicious',0)} malicioso(s), {vt.get('suspicious',0)} sospechoso(s)")
            if vt.get("categories"):
                print(f"     Cats: {', '.join(vt['categories'][:3])}")

        # Shodan
        sd = result.get("results", {}).get("shodan", {})
        if sd.get("success"):
            total = sd.get("total", 0)
            shown = len(sd.get("results", []))
            print(f"  🔍 Shodan: {total} servicios encontrados ({shown} mostrados)")

        # Censys
        cs = result.get("results", {}).get("censys", {})
        if cs.get("success"):
            total = cs.get("total", 0)
            shown = len(cs.get("results", []))
            print(f"  🌐 Censys: {total} hosts ({shown} mostrados)")

        time.sleep(1.5)

    # ─── GUARDAR ───
    os.makedirs("data", exist_ok=True)
    base = f"data/datos_reales_api_{ts}"

    # TXT Report
    rpath = base + ".txt"
    with open(rpath, "w", encoding="utf-8") as f:
        f.write("🛸 ORÁCULO DE INTELIGENCIA — EXTRACCIÓN MASIVA CON APIs REALES\n")
        f.write(f"Fecha: {datetime.now().isoformat()}\n")
        f.write(f"APIs: {', '.join(orchestrator.available_apis)}\n")
        f.write("=" * 80 + "\n\n")

        total_emails = 0
        total_mal = 0

        for domain, result in ALL.items():
            f.write(f"\n## {domain}\n")
            f.write("-" * 50 + "\n")

            hr = result.get("results", {}).get("hunter", {})
            if hr.get("success") and hr.get("emails"):
                elist = hr["emails"]
                total_emails += len(elist)
                f.write(f"\n📧 Emails ({len(elist)}):\n")
                for e in elist:
                    pos = e.get("position", "") or ""
                    f.write(f"  {e['value']:<40} conf:{e['confidence']}%  {e.get('type','')}  {pos[:30]}\n")

            vt = result.get("results", {}).get("virustotal", {})
            if vt.get("success"):
                m = vt.get("malicious", 0)
                total_mal += m
                f.write(f"\n🦠 VirusTotal: mal={m} sus={vt.get('suspicious',0)} rep={vt.get('reputation',0)}\n")
                if vt.get("categories"):
                    f.write(f"   Categorías: {', '.join(vt['categories'][:5])}\n")

            sd = result.get("results", {}).get("shodan", {})
            if sd.get("success") and sd.get("results"):
                f.write(f"\n🔍 Shodan ({sd.get('total',0)} total):\n")
                for r in sd["results"][:5]:
                    f.write(f"  {r['ip']:<16} port:{r['port']}  {r.get('org','')[:30]}\n")

            cs = result.get("results", {}).get("censys", {})
            if cs.get("success") and cs.get("results"):
                f.write(f"\n🌐 Censys ({cs.get('total',0)} hosts):\n")
                for h in cs["results"][:5]:
                    svcs = [f"{s.get('service_name','?')}/{s.get('port','?')}" for s in h.get('services',[])]
                    f.write(f"  {h['ip']:<16} {', '.join(svcs[:3])}\n")

            f.write("\n")

        f.write("=" * 80 + "\n")
        f.write("📊 RESUMEN GENERAL\n")
        f.write(f"  Dominios analizados: {len(DOMAINS)}\n")
        f.write(f"  📧 Emails descubiertos: {total_emails}\n")
        f.write(f"  🦠 Detecciones maliciosas: {total_mal}\n")
        f.write(f"  APIs usadas: {', '.join(orchestrator.available_apis)}\n")
        f.write("=" * 80 + "\n")

    # JSON
    jpath = base + ".json"
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump(ALL, f, indent=2, ensure_ascii=False, default=str)

    # CSV
    cpath = base + ".csv"
    with open(cpath, "w", encoding="utf-8") as f:
        f.write("email,dominio,confianza,tipo,cargo\n")
        for domain, result in ALL.items():
            hr = result.get("results", {}).get("hunter", {})
            if hr.get("success") and hr.get("emails"):
                for e in hr["emails"]:
                    pos = e.get("position", "").replace(",", " ") or ""
                    f.write(f"{e['value']},{domain},{e['confidence']},{e.get('type','')},{pos}\n")

    print(f"\n\n{'=' * 70}")
    print(f"  ✅  EXTRACCIÓN COMPLETADA: {datetime.now().isoformat()}")
    print(f"  {'=' * 66}")
    print(f"  📄 Reporte: {rpath}")
    print(f"  📄 JSON:    {jpath}")
    print(f"  📄 CSV:     {cpath}")
    print(f"{'=' * 70}")

if __name__ == "__main__":
    main()
