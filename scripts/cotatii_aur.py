#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
COTATII AUR — rulare in cloud (GitHub Actions), independent de PC si de Google.

Face doua lucruri la fiecare rulare (cron la 15 min):

  1. SNAPSHOT OFICIAL — daca e ora 08:00 sau 16:00 (ora Romaniei, zi lucratoare)
     si cotatia nu e deja in baza, o calculeaza si o salveaza in `cotatii_aur`.
     Recuperare pana la +3h, ca sa acopere intarzierile GitHub Actions.

  2. ALERTE DE PRET — compara pretul curent cu pragurile din `alerte_aur`
     si trimite mail prin Resend cand un prag e atins.

FORMULA (identica cu watcher_cotatii_aur.py de pe PC):
    24K RON/g = EUR_gram_brut x (curs_BNR - 0.02) x 0.985

Rulare locala pentru test:
    python scripts/cotatii_aur.py --test     (nu scrie in DB, nu trimite mailuri)
"""

import os, re, sys, json, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import urllib.request, urllib.error, urllib.parse

# ── CONFIG ──────────────────────────────────────────────────────────────────
SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
# cheie publishable — e oricum publica in perfecta.html; RLS e dezactivat pe tabele
# `or` (nu al doilea argument din .get) — in GitHub Actions un secret inexistent
# ajunge variabila SETATA dar GOALA, iar valoarea implicita n-ar mai fi folosita.
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"
RESEND_KEY   = os.environ.get("RESEND_API_KEY") or ""
FROM_EMAIL   = os.environ.get("FROM_EMAIL") or "Alerte Aur <onboarding@resend.dev>"
TG_TOKEN     = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
TG_CHAT      = os.environ.get("TELEGRAM_CHAT_ID") or ""

TZ = ZoneInfo("Europe/Bucharest")
SLOTS = ("08:00", "16:00")
ZILE_LUCRATOARE = (0, 1, 2, 3, 4)
CATCHUP_MAX_MIN = 180

AJUSTARE_CURS = 0.02
MARJA         = 0.985
OZ_IN_GRAME   = 31.1034768
COOLDOWN_ORE  = 12      # pentru alertele recurente (o_singura_data = false)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def log(msg):
    print(f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── HTTP ────────────────────────────────────────────────────────────────────
def http(url, metoda="GET", date=None, headere=None, timeout=30):
    h = {"User-Agent": UA}
    if headere:
        h.update(headere)
    corp = None
    if date is not None:
        corp = json.dumps(date).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=corp, headers=h, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # intorc raspunsul de eroare, ca sa decida apelantul (ex: tabela inca necreata)
        return e.code, e.read().decode("utf-8", "replace")


def supa(cale, metoda="GET", date=None, prefer=None):
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
    if prefer:
        h["Prefer"] = prefer
    return http(f"{SUPABASE_URL}/{cale}", metoda, date, h)


# ── SURSE DE PRET ───────────────────────────────────────────────────────────
def get_xau_usd():
    st, corp = http("https://api.gold-api.com/price/XAU")
    if st != 200:
        raise ValueError(f"gold-api a raspuns HTTP {st}")
    pret = float(json.loads(corp)["price"])
    if not (500 < pret < 50000):
        raise ValueError(f"pret XAU implauzibil: {pret}")
    return pret


def get_curs():
    """-> (eur_ron, usd_ron, sursa)"""
    try:
        _, html = http("https://www.cursbnr.ro/curs-valutar-bnr")
        def ext(cod):
            m = re.search(r'<option value="([0-9]+\.[0-9]+)"[^>]*>' + cod + r'</option>', html)
            return float(m.group(1)) if m else None
        eur, usd = ext("EUR"), ext("USD")
        if eur and usd:
            return eur, usd, "BNR (cursbnr.ro)"
        raise ValueError("nu gasesc EUR/USD in pagina")
    except Exception as e:
        log(f"  cursbnr.ro a esuat ({e}) — folosesc BCE ca rezerva")
        _, corp = http("https://api.frankfurter.dev/v1/latest?base=EUR&symbols=RON,USD")
        r = json.loads(corp)["rates"]
        eur_ron = float(r["RON"])
        return eur_ron, eur_ron / float(r["USD"]), "BCE (frankfurter) — REZERVA"


def calculeaza():
    xau = get_xau_usd()
    eur_ron, usd_ron, sursa = get_curs()
    eur_usd  = eur_ron / usd_ron
    eur_gram = (xau / eur_usd) / OZ_IN_GRAME
    curs_aj  = eur_ron - AJUSTARE_CURS
    p24      = eur_gram * curs_aj * MARJA
    return {
        "xau_usd": xau, "eur_usd": eur_usd, "eur_gram": eur_gram,
        "curs_bnr": eur_ron, "curs_ajustat": curs_aj, "p24": p24, "sursa": sursa,
    }


def randul(c, data_ref, slot):
    p = c["p24"]
    return {
        "data_ora":      f"{data_ref.strftime('%d.%m.%Y')} {slot}",
        "data_snapshot": data_ref.strftime("%Y-%m-%d"),
        "ora_snapshot":  slot,
        "eur_gram_brut": round(c["eur_gram"], 2),
        "curs_bnr":      round(c["curs_bnr"], 4),
        "curs_ajustat":  round(c["curs_ajustat"], 4),
        "pret_24k":      round(p, 2),
        "pret_22k":      round(p * 22 / 24, 2),
        "pret_18k":      round(p * 18 / 24, 2),
        "pret_14k":      round(p * 14 / 24, 2),
        "pret_12k":      round(p / 2, 2),
        "pret_8k":       round(p / 3, 2),
    }


# ── SNAPSHOT OFICIAL ────────────────────────────────────────────────────────
def slot_curent(acum):
    if acum.weekday() not in ZILE_LUCRATOARE:
        return None
    for slot in SLOTS:
        h, m = map(int, slot.split(":"))
        st = acum.replace(hour=h, minute=m, second=0, microsecond=0)
        if st <= acum <= st + timedelta(minutes=CATCHUP_MAX_MIN):
            return slot
    return None


def face_snapshot(c, acum, doar_test):
    slot = slot_curent(acum)
    if not slot:
        return False
    data_ora = f"{acum.strftime('%d.%m.%Y')} {slot}"
    st, corp = supa(f"cotatii_aur?data_ora=eq.{urllib.parse.quote(data_ora)}&select=id&limit=1")
    if st == 200 and json.loads(corp):
        log(f"  snapshot {data_ora}: exista deja")
        return False
    r = randul(c, acum, slot)
    log(f"  SNAPSHOT {data_ora} -> 24K {r['pret_24k']:.2f} RON/g")
    if doar_test:
        log("  (test — nu salvez)")
        return True
    st, corp = supa("cotatii_aur?on_conflict=data_ora", "POST", [r],
                    "resolution=merge-duplicates,return=minimal")
    if st in (200, 201, 204):
        log("  salvat in cotatii_aur")
        return True
    log(f"  EROARE salvare: HTTP {st} {corp[:200]}")
    return False


# ── ALERTE ──────────────────────────────────────────────────────────────────
def trimite_mail(catre, subiect, html):
    if not RESEND_KEY:
        log("  !! RESEND_API_KEY lipseste — nu pot trimite mail")
        return False
    try:
        st, corp = http("https://api.resend.com/emails", "POST",
                        {"from": FROM_EMAIL, "to": [catre], "subject": subiect, "html": html},
                        {"Authorization": f"Bearer {RESEND_KEY}"})
        if st in (200, 201):
            return True
        log(f"  EROARE Resend: HTTP {st} {corp[:200]}")
    except urllib.error.HTTPError as e:
        log(f"  EROARE Resend: HTTP {e.code} {e.read().decode('utf-8','replace')[:200]}")
    except Exception as e:
        log(f"  EROARE Resend: {e}")
    return False


def trimite_telegram(text):
    if not TG_TOKEN or not TG_CHAT:
        log("  !! TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID lipsesc — nu pot trimite pe Telegram")
        return False
    st, corp = http(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", "POST",
                    {"chat_id": TG_CHAT, "text": text,
                     "parse_mode": "HTML", "disable_web_page_preview": True})
    if st == 200:
        return True
    log(f"  EROARE Telegram: HTTP {st} {corp[:200]}")
    return False


def text_telegram(a, c, acum):
    p = c["p24"]
    sageata = "🔺" if a["directie"] == "peste" else "🔻"
    nota = f"\n<i>{a['eticheta']}</i>" if a.get("eticheta") else ""
    coada = ("Alerta s-a dezactivat automat." if a["o_singura_data"]
             else f"Urmatoarea notificare cel devreme peste {COOLDOWN_ORE}h.")
    return (
        f"{sageata} <b>ALERTA AUR</b>{nota}\n\n"
        f"24K a ajuns <b>{a['directie']}</b> pragul de <b>{a['prag']:,.2f}</b> RON/g\n\n"
        f"<b>Acum: {p:,.2f} RON/gram</b>\n"
        f"<code>22K {p*22/24:8,.2f}\n"
        f"18K {p*18/24:8,.2f}\n"
        f"14K {p*14/24:8,.2f}\n"
        f"12K {p/2:8,.2f}\n"
        f" 8K {p/3:8,.2f}</code>\n\n"
        f"<i>{acum.strftime('%d.%m.%Y %H:%M')} · spot {c['xau_usd']:,.2f} USD/oz · "
        f"curs BNR {c['curs_bnr']:.4f}</i>\n{coada}"
    )


def corp_mail(a, c, acum):
    p = c["p24"]
    sageata = "↑" if a["directie"] == "peste" else "↓"
    return f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#1e293b">
  <div style="background:#1F3864;color:#fff;padding:16px 20px;border-radius:10px 10px 0 0">
    <h2 style="margin:0;font-size:17px">🔔 Alertă preț aur</h2>
  </div>
  <div style="border:1px solid #e2e8f0;border-top:none;border-radius:0 0 10px 10px;padding:20px">
    <p style="margin:0 0 14px;font-size:15px">
      Aurul <b>24K</b> a ajuns {sageata} <b>{a['directie']}</b> pragul tău de
      <b>{a['prag']:,.2f} RON/gram</b>.
    </p>
    <div style="background:#fef3c7;border-left:5px solid #FFD700;border-radius:8px;padding:16px;text-align:center;margin-bottom:16px">
      <div style="font-size:11px;color:#64748b;font-weight:700;text-transform:uppercase">Preț acum — 24K</div>
      <div style="font-size:34px;font-weight:800;color:#856404">{p:,.2f}</div>
      <div style="font-size:12px;color:#64748b">RON / gram</div>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <tr><td style="padding:5px 0">22K</td><td style="text-align:right;font-weight:700">{p*22/24:,.2f}</td></tr>
      <tr><td style="padding:5px 0">18K</td><td style="text-align:right;font-weight:700">{p*18/24:,.2f}</td></tr>
      <tr><td style="padding:5px 0">14K</td><td style="text-align:right;font-weight:700">{p*14/24:,.2f}</td></tr>
      <tr><td style="padding:5px 0">12K</td><td style="text-align:right;font-weight:700">{p/2:,.2f}</td></tr>
      <tr><td style="padding:5px 0">8K</td><td style="text-align:right;font-weight:700">{p/3:,.2f}</td></tr>
    </table>
    <p style="font-size:11px;color:#64748b;margin-top:16px;line-height:1.7">
      {acum.strftime('%d.%m.%Y %H:%M')} · aur spot {c['xau_usd']:,.2f} USD/uncie ·
      EUR/USD {c['eur_usd']:.4f} · curs BNR {c['curs_bnr']:.4f}<br>
      {'Alerta s-a dezactivat automat (era setată o singură dată).' if a['o_singura_data'] else f'Următoarea notificare cel devreme peste {COOLDOWN_ORE} ore.'}
    </p>
  </div>
</div>"""


def verifica_alerte(c, acum, doar_test):
    st, corp = supa("alerte_aur?activa=eq.true&select=*")
    if st == 404:
        log("  tabela `alerte_aur` nu exista inca — ruleaza sql/alerte_aur.sql in Supabase")
        return 0
    if st != 200:
        log(f"  nu pot citi alertele: HTTP {st} {corp[:200]}")
        return 0
    alerte = json.loads(corp)
    if not alerte:
        log("  nicio alertă activă")
        return 0

    p = c["p24"]
    declansate = 0
    for a in alerte:
        prag = float(a["prag"])
        atins = (p >= prag) if a["directie"] == "peste" else (p <= prag)
        if not atins:
            continue

        # cooldown pentru alertele recurente
        if not a["o_singura_data"] and a.get("ultima_declansare"):
            try:
                ult = datetime.fromisoformat(a["ultima_declansare"].replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - ult) < timedelta(hours=COOLDOWN_ORE):
                    continue
            except Exception:
                pass

        et = a.get("eticheta") or f"{a['directie']} {prag:,.2f}"
        canale = ([f"telegram"] if a.get("telegram") else []) + ([a["email"]] if a.get("email") else [])
        log(f"  ALERTA DECLANSATA: {et} (prag {prag:.2f}, pret {p:.2f}) -> {', '.join(canale) or 'niciun canal'}")
        if doar_test:
            declansate += 1
            continue

        # trimit pe toate canalele alese; e destul sa reuseasca unul
        trimis = False
        if a.get("telegram"):
            trimis = trimite_telegram(text_telegram(a, c, acum)) or trimis
        if a.get("email"):
            sub = f"🔔 Aur 24K {p:,.2f} RON/g — {a['directie']} {prag:,.2f}"
            trimis = trimite_mail(a["email"], sub, corp_mail(a, c, acum)) or trimis
        if not trimis:
            log("  nu am reusit pe niciun canal — reincerc la rularea urmatoare")
            continue

        patch = {"ultima_declansare": datetime.now(timezone.utc).isoformat(),
                 "pret_declansare": round(p, 2)}
        if a["o_singura_data"]:
            patch["activa"] = False
        supa(f"alerte_aur?id=eq.{a['id']}", "PATCH", patch, "return=minimal")
        declansate += 1
    return declansate


# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="nu scrie in DB si nu trimite mailuri")
    args = ap.parse_args()

    acum = datetime.now(TZ)
    log(f"Rulare {'TEST ' if args.test else ''}— {acum.strftime('%A %d.%m.%Y %H:%M')} (Europe/Bucharest)")

    try:
        c = calculeaza()
    except Exception as e:
        log(f"EROARE la calculul pretului: {e}")
        sys.exit(1)

    log(f"  24K = {c['p24']:.2f} RON/g  (XAU {c['xau_usd']:.2f} USD/oz, "
        f"EUR/USD {c['eur_usd']:.4f}, curs {c['curs_bnr']:.4f} — {c['sursa']})")

    face_snapshot(c, acum, args.test)
    n = verifica_alerte(c, acum, args.test)
    log(f"Gata. {n} alerte declansate.")


if __name__ == "__main__":
    main()
