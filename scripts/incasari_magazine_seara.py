#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INCASARI MAGAZINE SEARA — mesaj Telegram zilnic la 19:30 ora Romaniei cu:
- Incasari CASH per magazin (din raportul Z: cash_z_c1 + cash_z_c2)
- Incasari CARD per magazin (din raportul Z: card_z_c1 + card_z_c2)
- Total CASH + CARD + Total ZI

Destinatar: Eugen pe Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID).

Ruleaza in GitHub Actions cu cron des in fereastra 16-18 UTC (acopera ora de vara si iarna).
Scriptul verifica ora Romaniei si trimite DOAR daca e dupa 19:30 exact. Idempotent via alerte_zilnice.
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"

TELEGRAM_BOT_TOKEN = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

TZ = ZoneInfo("Europe/Bucharest")


def log(msg):
    print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def http(url, method="GET", data=None, timeout=30, headers=None):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    hdrs = headers or {}
    if body:
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
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


def marcheaza_trimis(tip, data_str):
    """INSERT idempotent in alerte_zilnice. True = prima trimitere azi, False = deja trimis."""
    hdrs = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation,resolution=ignore-duplicates",
    }
    body = json.dumps([{"tip": tip, "data": data_str}]).encode("utf-8")
    req = urllib.request.Request(
        SUPABASE_URL + "/alerte_zilnice",
        data=body, method="POST", headers=hdrs
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            corp = r.read().decode("utf-8", errors="replace")
            arr = json.loads(corp) if corp else []
            return len(arr) > 0
    except Exception as e:
        log(f"EROARE marcheaza_trimis: {e}")
        return False


def fmt_ron(n):
    # Format romanesc: 2.922,90
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def trimite_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("!! TELEGRAM_BOT_TOKEN sau TELEGRAM_CHAT_ID lipsesc")
        return False
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
    }
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read().decode("utf-8", errors="replace"))
            if resp.get("ok"):
                log("Telegram: trimis OK")
                return True
            log(f"Telegram ESUAT: {resp}")
            return False
    except Exception as e:
        log(f"Telegram EROARE: {e}")
        return False


def main():
    acum = datetime.now(TZ)
    today = acum.date().isoformat()
    run_manual = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"

    # Trimite DOAR dupa 19:30 ora Romaniei. Cron ruleaza des in fereastra 16-18 UTC.
    if not run_manual:
        if acum.hour < 19 or (acum.hour == 19 and acum.minute < 30):
            log(f"Nu e inca 19:30 in Romania (e {acum:%H:%M}), skip")
            return 0

    if run_manual:
        log(f"Rulare manuala fortata la {acum:%H:%M} (fara guard idempotenta)")
    else:
        prima_data = marcheaza_trimis("INCASARI_SEARA", today)
        if not prima_data:
            log(f"Deja am trimis INCASARI_SEARA azi ({today}), skip")
            return 0
        log(f"Prima rulare pentru azi ({today} {acum:%H:%M}), trimit")

    try:
        rows = api(
            f"/borderouri?select=magazin,cash_z_c1,cash_z_c2,card_z_c1,card_z_c2"
            f"&data=eq.{today}&order=magazin.asc"
        )
    except Exception as e:
        log(f"EROARE la fetch borderouri: {e}")
        return 1

    log(f"Borderouri gasite azi: {len(rows)}")

    if not rows:
        txt = (
            f"💰 *ÎNCASĂRI ARAFURA — {acum:%d.%m.%Y}*\n\n"
            f"⚠ *Niciun borderou primit azi!*"
        )
        ok = trimite_telegram(txt)
        return 0 if ok else 1

    # Agregare pe magazin (prudential — sumez daca sunt multiple borderouri/magazin)
    agregat = {}
    for r in rows:
        mag = r.get("magazin") or "?"
        cash = float(r.get("cash_z_c1") or 0) + float(r.get("cash_z_c2") or 0)
        card = float(r.get("card_z_c1") or 0) + float(r.get("card_z_c2") or 0)
        if mag not in agregat:
            agregat[mag] = {"cash": 0.0, "card": 0.0}
        agregat[mag]["cash"] += cash
        agregat[mag]["card"] += card

    total_cash = sum(v["cash"] for v in agregat.values())
    total_card = sum(v["card"] for v in agregat.values())
    total_zi = total_cash + total_card

    # Sortare descrescator dupa total
    magazine_sortate = sorted(
        agregat.items(),
        key=lambda x: x[1]["cash"] + x[1]["card"],
        reverse=True,
    )

    lines = []
    for mag, v in magazine_sortate:
        mag_scurt = mag[:10].ljust(10)
        cash_str = fmt_ron(v["cash"]).rjust(10)
        card_str = fmt_ron(v["card"]).rjust(10)
        lines.append(f"{mag_scurt} {cash_str} {card_str}")

    tabel = "\n".join(lines)
    sep = "─" * 32

    txt = (
        f"💰 *ÎNCASĂRI ARAFURA — {acum:%d.%m.%Y}*\n\n"
        f"```\n"
        f"Magazin        Cash       Card\n"
        f"{sep}\n"
        f"{tabel}\n"
        f"{sep}\n"
        f"TOTAL      {fmt_ron(total_cash).rjust(10)} {fmt_ron(total_card).rjust(10)}\n"
        f"```\n"
        f"🧾 *TOTAL ZI: {fmt_ron(total_zi)} RON*\n"
        f"📋 {len(agregat)} borderouri primite"
    )

    log(f"Total cash: {total_cash:.2f} | Card: {total_card:.2f} | ZI: {total_zi:.2f}")
    ok = trimite_telegram(txt)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
