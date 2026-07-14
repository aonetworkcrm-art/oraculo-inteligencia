"""
╔══════════════════════════════════════════════════════════════╗
║  EXTRACCIÓN DIRECTA — Hunter.io + VirusTotal                ║
║  Sin IntelOrchestrator — llamadas directas a las APIs       ║
║  Guarda en data/ con timestamp                              ║
╚══════════════════════════════════════════════════════════════╝
"""
import sys, os, json, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from intel_connectors import HunterConnector, VirusTotalConnector

DOMAINS = [
    "comcast.com", "xfinity.com", "verizon.com", "att.com",
    "microsoft.com", "google.com", "apple.com",
    "facebook.com", "linkedin.com", "sbcglobal.net",
]

def main():
    hunter = HunterConnector()
    vt = VirusTotalConnector()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print("  🛸  EXTRACCIÓN DIRECTA CON APIs REALES")
    print(f"  Inicio: {datetime.now().isoformat()}")
    print(f"  Hunter: {'✅' if hunter.enabled else '❌'}  VirusTotal: {'✅' if vt.enabled else '❌'}")
    print(f"  Dominios: {len(DOMAINS)}")
    print("=" * 70)

    ALL_EMAILS = []
    ALL_VT = {}

    for i, domain in enumerate(DOMAINS, 1):
        print(f"\n{'─' * 50}")
        print(f"[{i}/{len(DOMAINS)}] 🔍 {domain}")

        # ─── Hunter.io ───
        try:
            hr = hunter.domain_search(domain, limit=10)
            if hr.get("success") and hr.get("emails"):
                emails = hr["emails"]
                print(f"  📧 Hunter: {len(emails)} emails")
                for e in emails:
                    pos = e.get("position", "") or ""
                    print(f"     {e['value']:<45} conf:{e['confidence']}%  {pos[:25]}")
                    ALL_EMAILS.append({
                        "email": e["value"],
                        "domain": domain,
                        "confidence": e["confidence"],
                        "type": e.get("type", ""),
                        "position": pos,
                    })
            else:
                print(f"  📧 Hunter: {hr.get('error', 'no results')}")
        except Exception as ex:
            print(f"  📧 Hunter ERROR: {ex}")

        # ─── VirusTotal ───
        try:
            vt_result = vt.analyze_domain(domain) if vt.enabled else {"success": False}
            if vt_result.get("success"):
                m = vt_result.get("malicious", 0)
                s = vt_result.get("suspicious", 0)
                rep = vt_result.get("reputation", 0)
                cats = ", ".join(vt_result.get("categories", [])[:3])
                print(f"  🦠 VT: mal={m} sus={s} rep={rep}  [{cats}]")
                ALL_VT[domain] = {
                    "malicious": m,
                    "suspicious": s,
                    "harmless": vt_result.get("harmless", 0),
                    "reputation": rep,
                    "categories": vt_result.get("categories", []),
                }
            else:
                print(f"  🦠 VT: {vt_result.get('error', 'no data')}")
        except Exception as ex:
            print(f"  🦠 VT ERROR: {ex}")

        time.sleep(1.5)

    # ─── GUARDAR ARCHIVOS ───
    os.makedirs("data", exist_ok=True)
    base = f"data/extraccion_directa_{ts}"

    # TXT Report
    rpath = base + ".txt"
    with open(rpath, "w", encoding="utf-8") as f:
        f.write("🛸 EXTRACCIÓN DIRECTA CON APIs REALES\n")
        f.write(f"Fecha: {datetime.now().isoformat()}\n")
        f.write(f"Hunter.io: {'OK' if hunter.enabled else 'N/A'}\n")
        f.write(f"VirusTotal: {'OK' if vt.enabled else 'N/A'}\n")
        f.write("=" * 80 + "\n\n")

        f.write("╔════════════════════════════════════════════════════╗\n")
        f.write("║  📧 EMAILS REALES — Hunter.io                    ║\n")
        f.write("╚════════════════════════════════════════════════════╝\n\n")
        for e in ALL_EMAILS:
            f.write(f"  {e['email']:<45} conf:{e['confidence']}%  {e.get('type',''):<10}  {e['position'][:30]}\n")

        if not ALL_EMAILS:
            f.write("  (no se encontraron emails)\n")

        f.write("\n╔════════════════════════════════════════════════════╗\n")
        f.write("║  🦠 VIRUSTOTAL — ANÁLISIS DE AMENAZAS            ║\n")
        f.write("╚════════════════════════════════════════════════════╝\n\n")
        for domain, data in ALL_VT.items():
            f.write(f"  {domain}\n")
            f.write(f"    Malicious:  {data.get('malicious', 0)}\n")
            f.write(f"    Suspicious: {data.get('suspicious', 0)}\n")
            f.write(f"    Harmless:   {data.get('harmless', 0)}\n")
            f.write(f"    Reputation: {data.get('reputation', 0)}\n")
            if data.get("categories"):
                f.write(f"    Categories: {', '.join(data['categories'][:5])}\n")
            f.write("\n")

        f.write("=" * 80 + "\n")
        f.write(f"📊 RESUMEN: {len(ALL_EMAILS)} emails · {len(ALL_VT)} dominios analizados\n")
        f.write("=" * 80 + "\n")

    # CSV
    cpath = base + ".csv"
    with open(cpath, "w", encoding="utf-8") as f:
        f.write("email,dominio,confianza,tipo,cargo\n")
        for e in ALL_EMAILS:
            cargo = e.get("position", "").replace(",", " ").replace("\n", " ")
            f.write(f"{e['email']},{e['domain']},{e['confidence']},{e.get('type','')},{cargo}\n")

    # JSON
    jpath = base + ".json"
    with open(jpath, "w", encoding="utf-8") as f:
        json.dump({"emails": ALL_EMAILS, "virustotal": ALL_VT}, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"  ✅  EXTRACCIÓN COMPLETADA")
    print(f"  {'=' * 66}")
    print(f"  📧 Emails encontrados: {len(ALL_EMAILS)}")
    print(f"  🦠 Dominios analizados: {len(ALL_VT)}")
    print(f"  📄 Reporte: {rpath}")
    print(f"  📄 CSV:     {cpath}")
    print(f"  📄 JSON:    {jpath}")
    print(f"{'=' * 70}")

    # Show all emails
    if ALL_EMAILS:
        print(f"\n📋 TODOS LOS EMAILS ENCONTRADOS:")
        print(f"{'─' * 60}")
        for e in ALL_EMAILS:
            print(f"  📧 {e['email']:<40} conf:{e['confidence']}%")

if __name__ == "__main__":
    main()
