#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTE EXPIRARE CONTRACTE — DOMADAMI.

Problema pe care o rezolva: contractele de inchiriere se fac pe 1 an, apoi se
prelungesc anual prin act aditional, si toata lumea uita ca expira.

Ruleaza o data pe zi si anunta la **30** si **7** zile inainte de expirare, plus
in ziua in care un act a expirat deja.

Valabilitatea reala a unui chirias = ULTIMUL act din lantul lui (contract →
act aditional 1 → act aditional 2), nu contractul initial.

Canale: WhatsApp catre Eugen (CallMeBot) + email catre Bogdan si Vivi (Resend).

Rulare:
    python scripts/contracte_domadami.py            # verifica si notifica
    python scripts/contracte_domadami.py --test     # doar afiseaza
"""

import os, sys, json, argparse
from datetime import datetime, date, timedelta
import urllib.request, urllib.error, urllib.parse

SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"
RESEND_KEY   = os.environ.get("RESEND_API_KEY") or ""
FROM_EMAIL   = os.environ.get("FROM_EMAIL") or "Alerte DOMADAMI <onboarding@resend.dev>"

PRAGURI = (30, 7)          # cu cate zile inainte anunt
EMAIL_ECHIPA = [e.strip() for e in (os.environ.get("DOMADAMI_EMAILURI") or "").split(",") if e.strip()]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def log(m): print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def http(url, metoda="GET", date_=None, headere=None, timeout=45):
    h = {"User-Agent": UA}
    if headere: h.update(headere)
    corp = json.dumps(date_, ensure_ascii=False).encode("utf-8") if date_ is not None else None
    if corp: h.setdefault("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=corp, headers=h, method=metoda), timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def supa(cale):
    return http(f"{SUPABASE_URL}/{cale}", headere={"apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}"})


def destinatari_whatsapp():
    lista = []
    for sufix in ("", "_2", "_3", "_4", "_5"):
        tel = (os.environ.get(f"CALLMEBOT_PHONE{sufix}") or "").strip()
        key = (os.environ.get(f"CALLMEBOT_APIKEY{sufix}") or "").strip()
        if tel and key: lista.append((tel, key))
    return lista


def trimite_whatsapp(text):
    dest = destinatari_whatsapp()
    if not dest:
        log("  !! fara destinatari WhatsApp configurati"); return False
    ok = 0
    for tel, key in dest:
        url = ("https://api.callmebot.com/whatsapp.php?"
               + urllib.parse.urlencode({"phone": tel, "text": text, "apikey": key}))
        st, corp = http(url, timeout=45)
        if st == 200 and "error" not in corp.lower()[:400]:
            ok += 1
        else:
            log(f"    WhatsApp ...{tel[-4:]}: ESUAT (HTTP {st})")
    return ok > 0


def trimite_mail(catre, subiect, html):
    if not RESEND_KEY or not catre: return False
    st, corp = http("https://api.resend.com/emails", "POST",
                    {"from": FROM_EMAIL, "to": catre, "subject": subiect, "html": html},
                    {"Authorization": f"Bearer {RESEND_KEY}"})
    if st in (200, 201): return True
    log(f"  EROARE Resend: HTTP {st} {corp[:200]}")
    return False


def aduna_stari():
    """-> lista de (chirias, ultim_act, zile_ramase), doar chiriasi activi."""
    st, corp = supa("domadami_documente?select=*")
    if st != 200:
        log(f"  nu pot citi documentele: HTTP {st} {corp[:200]}"); return None
    docs = json.loads(corp)
    st, corp = supa("domadami_chiriasi?select=id,nume,activ,observatii")
    if st != 200:
        log(f"  nu pot citi chiriasii: HTTP {st}"); return None
    chiriasi = {c["id"]: c for c in json.loads(corp) if c.get("activ")}

    ultim = {}
    for d in docs:
        cid = d.get("chirias_id")
        if cid not in chiriasi: continue
        if cid not in ultim or (d.get("valabil_pana") or "") > (ultim[cid].get("valabil_pana") or ""):
            ultim[cid] = d

    azi = date.today()
    out = []
    for cid, act in ultim.items():
        try:
            exp = date.fromisoformat(act["valabil_pana"])
        except Exception:
            continue
        out.append((chiriasi[cid], act, (exp - azi).days))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    stari = aduna_stari()
    if stari is None: sys.exit(1)
    if not stari:
        log("Niciun act introdus inca — nimic de verificat."); return

    de_anuntat = [(c, a, z) for c, a, z in stari if z in PRAGURI or z == 0]
    expirate   = [(c, a, z) for c, a, z in stari if z < 0]

    log(f"{len(stari)} chiriasi cu acte | {len(de_anuntat)} de anuntat azi | {len(expirate)} deja expirate")
    for c, a, z in sorted(stari, key=lambda x: x[2]):
        marcaj = "  <-- ANUNT AZI" if (z in PRAGURI or z == 0) else ("  [expirat]" if z < 0 else "")
        log(f"   {c['nume'][:28]:<30} pana la {a['valabil_pana']}  {z:>5} zile{marcaj}")

    if not de_anuntat:
        log("Nimic de trimis azi."); return

    linii = []
    for c, a, z in sorted(de_anuntat, key=lambda x: x[2]):
        tip = "Contract" if a.get("tip") == "contract" else "Act aditional"
        cand = "EXPIRA AZI" if z == 0 else f"expira in {z} zile"
        linii.append(f"• {c['nume']} ({c.get('observatii') or '—'})\n  {tip} {a.get('numar') or ''} — {cand}, pe {a['valabil_pana']}")
    corp_txt = "\n\n".join(linii)

    if args.test:
        print("\n--- mesajul care s-ar trimite ---\n")
        print(f"CONTRACTE DOMADAMI\n\n{corp_txt}\n\nPregatiti actele aditionale.")
        log("MOD TEST — nu trimit nimic"); return

    text = (f"📁 *CONTRACTE DOMADAMI*\n\n{corp_txt}\n\n"
            f"Pregatiti actele aditionale.")
    if trimite_whatsapp(text): log("  WhatsApp trimis")

    if EMAIL_ECHIPA:
        html = ("<div style=\"font-family:Arial,sans-serif;max-width:560px\">"
                "<h2 style=\"color:#1F3864\">📁 Contracte DOMADAMI — expira in curand</h2>"
                + "".join(f"<p style=\"border-left:4px solid #f59e0b;padding-left:10px\">{l.replace(chr(10),'<br>')}</p>"
                          for l in linii)
                + "<p style=\"font-size:12px;color:#64748b\">Mesaj automat. Pregatiti actele aditionale.</p></div>")
        if trimite_mail(EMAIL_ECHIPA, f"DOMADAMI — {len(de_anuntat)} contracte expira in curand", html):
            log(f"  email trimis catre {len(EMAIL_ECHIPA)} destinatari")


if __name__ == "__main__":
    main()
