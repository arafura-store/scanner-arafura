#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SOLD CAIET SEARA — mesaj WhatsApp zilnic la 20:00 ora Romaniei cu:
- Sold CURENT (real, exclude PENDING)
- Sold PREVIZIONAT (proiectat, include PENDING)
- Numarul si suma operatiunilor PENDING (de confirmat)

Destinatar: doar Eugen (CALLMEBOT_PHONE — primul numar din secrets).

Ruleaza in GitHub Actions cu cron la 17:00 si 18:00 UTC (acopera si ora de vara si iarna).
Scriptul verifica ora Romaniei si trimite DOAR daca e ora 20 exact.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"

# Destinatari WhatsApp — loop prin CALLMEBOT_PHONE, _2, _3... (pana la 5).
# Pentru sold caiet, workflow-ul paseaza perechi dedicate (nu se amesteca cu cotatii aur).
def _destinatari():
    lista = []
    for sufix in ("", "_2", "_3", "_4", "_5"):
        tel = (os.environ.get(f"CALLMEBOT_PHONE{sufix}") or "").strip()
        key = (os.environ.get(f"CALLMEBOT_APIKEY{sufix}") or "").strip()
        if tel and key:
            lista.append((tel, key))
    return lista

DESTINATARI = _destinatari()

TZ = ZoneInfo("Europe/Bucharest")


def log(msg):
    print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def http(url, method="GET", data=None, timeout=30, headers=None):
    body = json.dumps(data).encode() if data is not None else None
    hdrs = headers or {}
    if body:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode("utf-8", errors="replace")
        except Exception:
            return e.code, str(e)
    except Exception as e:
        return 0, str(e)


def api(path):
    hdrs = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    st, body = http(SUPABASE_URL + path, headers=hdrs)
    if st != 200:
        raise RuntimeError(f"API {path} -> HTTP {st}: {body[:200]}")
    return json.loads(body)


def fmt_ron(n):
    # Format romanesc: 34 905,00 RON
    return f"{n:,.2f}".replace(",", " ").replace(".", ",") + " RON"


def trimite_whatsapp(text):
    if not DESTINATARI:
        log("!! Nici un destinatar configurat (CALLMEBOT_PHONE + APIKEY lipsesc)")
        return False
    reusite = 0
    for tel, key in DESTINATARI:
        url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode({
            "phone": tel, "text": text, "apikey": key
        })
        st, corp = http(url, timeout=45)
        masca = f"...{tel[-4:]}"
        if st == 200 and "error" not in corp.lower()[:400]:
            reusite += 1
            log(f"WhatsApp -> {masca}: trimis")
        else:
            log(f"WhatsApp -> {masca}: ESUAT (HTTP {st}) {corp[:200]}")
    return reusite > 0


def calculeaza_sold():
    """Fetch caiet activ (data <= azi) si calculeaza sold curent + previzionat."""
    today = datetime.now(TZ).date().isoformat()
    all_rows = []
    offset = 0
    while True:
        rows = api(
            f"/caiet?select=intrare,iesire,tip&data=lte.{today}"
            f"&sters_la=is.null&limit=1000&offset={offset}"
        )
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < 1000:
            break
        offset += 1000

    sold_curent = 0.0
    sold_proiectat = 0.0
    nr_pending = 0
    delta_pending = 0.0

    for r in all_rows:
        tip = r.get("tip") or ""
        if "CONFIRMAT" in tip:
            continue
        d = float(r.get("intrare") or 0) - float(r.get("iesire") or 0)
        sold_proiectat += d
        if "PENDING" in tip:
            nr_pending += 1
            delta_pending += d
        else:
            sold_curent += d

    return sold_curent, sold_proiectat, nr_pending, delta_pending


def main():
    acum = datetime.now(TZ)

    # Rulare manuala (buton "Run workflow" din GitHub Actions) → sare peste verificare ora.
    # Folositor pentru testare imediata fara sa astepti pana la 20:00.
    run_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    # Trimite DOAR la ora 20 (Romania) — cron ruleaza la 17 UTC + 18 UTC ca sa
    # acopere si ora de vara (UTC+3) si iarna (UTC+2). Un singur mesaj/zi.
    if not run_manual and acum.hour != 20:
        log(f"Nu e ora 20:00 in Romania (e {acum:%H:%M}), skip trimitere")
        return 0
    if run_manual and acum.hour != 20:
        log(f"Rulare manuala fortata la {acum:%H:%M} (in mod normal doar 20:00)")

    # Nu trimit in weekend (sambata/duminica) - restaurantul are alt program;
    # daca vrei si weekend, scoate conditia asta.
    # Comentat momentan — trimit in fiecare zi
    # if acum.weekday() >= 5:
    #     log("Weekend, skip trimitere")
    #     return 0

    try:
        sold_curent, sold_proiectat, nr_pending, delta_pending = calculeaza_sold()
    except Exception as e:
        log(f"EROARE la calcul sold: {e}")
        return 1

    log(f"Sold curent: {sold_curent:.2f} | Previzionat: {sold_proiectat:.2f} | PENDING: {nr_pending} ({delta_pending:+.2f})")

    txt = (
        f"📒 *CAIET ARAFURA — {acum:%d.%m.%Y} seara*\n\n"
        f"💰 Sold curent:      *{fmt_ron(sold_curent)}*\n"
        f"⏳ Sold previzionat: *{fmt_ron(sold_proiectat)}*\n\n"
    )
    if nr_pending > 0:
        semn = "+" if delta_pending >= 0 else ""
        txt += f"📋 {nr_pending} operațiuni PENDING ({semn}{fmt_ron(delta_pending)} de confirmat)"
    else:
        txt += "✅ Nici o operațiune PENDING"

    ok = trimite_whatsapp(txt)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
