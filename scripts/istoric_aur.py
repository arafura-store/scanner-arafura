#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ISTORIC AUR ZILNIC — umple si actualizeaza tabela `istoric_aur_zilnic`.

Foloseste doua surse gratuite:
  - aur:    Yahoo Finance, contractul GC=F (aur la COMEX), inchideri zilnice
  - valute: frankfurter.dev (curs de referinta BCE), serie de timp EUR→RON si EUR→USD

Din ele calculeaza pretul in lei cu ACEEASI formula ca restul aplicatiei:
    EUR/gram = (XAU_USD / (EUR_RON / USD_RON)) / 31.1034768
    24K RON/g = EUR/gram x (EUR_RON - 0.02) x 0.985

De ce e nevoie de asta: browserul nu poate cere direct de la Yahoo (nu trimit
antete CORS), deci datele se aduc aici si se citesc din Supabase.

VERIFICAT pe cele 88 de zile in care avem si cotatii proprii: raportul mediu intre
pretul nostru real si aceasta serie e 1.0037, adica practic 1 — NU exista decalaj
sistematic, deci seria nu trebuie calibrata. Abaterile (±2%) vin din momentul zilei:
noi masuram la 00:00/08:00/16:00, aici e inchiderea sesiunii. Diferenta intre ele e
miscarea normala intra-zi a aurului, nu o eroare.

Cursul e cel BCE, nu BNR (BNR nu mai publica serie istorica accesibila). Sub 0.1% diferenta.

Rulare:
    python scripts/istoric_aur.py --ani 5     # umplere initiala
    python scripts/istoric_aur.py --zile 10   # improspatare (implicit)
    python scripts/istoric_aur.py --test      # nu scrie nimic
"""

import os, sys, json, time, argparse
from datetime import datetime, date, timedelta, timezone
import urllib.request, urllib.error, urllib.parse

SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"
TABEL = "istoric_aur_zilnic"

AJUSTARE_CURS = 0.02
MARJA         = 0.985
OZ_IN_GRAME   = 31.1034768
BATCH         = 500

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def http(url, metoda="GET", date_=None, headere=None, timeout=60):
    h = {"User-Agent": UA}
    if headere:
        h.update(headere)
    corp = None
    if date_ is not None:
        corp = json.dumps(date_).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=corp, headers=h, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def cu_reincercari(fn, nume, incercari=3, pauza=8):
    ultima = None
    for i in range(1, incercari + 1):
        try:
            return fn()
        except Exception as e:
            ultima = e
            log(f"  {nume}: incercarea {i}/{incercari} a esuat ({e})")
            if i < incercari:
                time.sleep(pauza)
    raise ultima


# ── SURSE ───────────────────────────────────────────────────────────────────
def aur_zilnic(interval):
    """{date: close_usd} de la Yahoo (GC=F)."""
    st, corp = http(f"https://query1.finance.yahoo.com/v8/finance/chart/GC=F?range={interval}&interval=1d")
    if st != 200:
        raise ValueError(f"Yahoo a raspuns HTTP {st}")
    r = json.loads(corp)["chart"]["result"][0]
    ts = r["timestamp"]
    inch = r["indicators"]["quote"][0]["close"]
    out = {}
    for t, c in zip(ts, inch):
        if c is None:
            continue
        out[datetime.fromtimestamp(t, timezone.utc).date()] = float(c)
    return out


def valute_zilnic(de_la, pana_la):
    """{date: (eur_ron, eur_usd)} de la frankfurter, pe bucati de cate un an."""
    out = {}
    cursor = de_la
    while cursor <= pana_la:
        capat = min(cursor + timedelta(days=365), pana_la)
        url = (f"https://api.frankfurter.dev/v1/{cursor}..{capat}"
               f"?base=EUR&symbols=RON,USD")
        st, corp = http(url)
        if st != 200:
            raise ValueError(f"frankfurter HTTP {st} pentru {cursor}..{capat}")
        for zi, v in json.loads(corp).get("rates", {}).items():
            if "RON" in v and "USD" in v:
                out[date.fromisoformat(zi)] = (float(v["RON"]), float(v["USD"]))
        cursor = capat + timedelta(days=1)
        time.sleep(0.3)
    return out


# ── CONSTRUIRE SERIE ────────────────────────────────────────────────────────
def construieste(aur, valute):
    """Imbina cele doua serii. Aurul se tranzactioneaza si in zile in care BCE
    nu publica curs (sarbatori) — pentru acelea folosesc ultimul curs cunoscut."""
    randuri = []
    zile_valuta = sorted(valute)
    ultim = None
    lipsa = 0
    for zi in sorted(aur):
        # ultimul curs publicat la data sau inainte de ea
        while zile_valuta and zile_valuta[0] <= zi:
            ultim = valute[zile_valuta.pop(0)]
        if ultim is None:
            lipsa += 1
            continue
        eur_ron, eur_usd = ultim
        usd_ron = eur_ron / eur_usd
        xau = aur[zi]
        eur_gram = (xau / eur_usd) / OZ_IN_GRAME
        ron_gram = eur_gram * (eur_ron - AJUSTARE_CURS) * MARJA
        randuri.append({
            "data": zi.isoformat(),
            "xau_usd": round(xau, 2),
            "eur_ron": round(eur_ron, 4),
            "usd_ron": round(usd_ron, 4),
            "eur_gram": round(eur_gram, 2),
            "ron_gram_24k": round(ron_gram, 2),
        })
    if lipsa:
        log(f"  {lipsa} zile sarite (nu aveam inca niciun curs publicat inainte de ele)")
    return randuri


def salveaza(randuri):
    url = f"{SUPABASE_URL}/{TABEL}?on_conflict=data"
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Content-Type": "application/json",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
    for i in range(0, len(randuri), BATCH):
        lot = randuri[i:i + BATCH]
        st, corp = http(url, "POST", lot, h)
        if st not in (200, 201, 204):
            log(f"  EROARE salvare (lot {i//BATCH+1}): HTTP {st} {corp[:250]}")
            return False
    return True


def main():
    ap = argparse.ArgumentParser(description="Istoric aur zilnic -> Supabase")
    ap.add_argument("--ani", type=int, help="umplere initiala, cati ani in urma (ex: 5)")
    ap.add_argument("--zile", type=int, default=10, help="improspatare: ultimele N zile (implicit 10)")
    ap.add_argument("--test", action="store_true", help="nu scrie in baza")
    args = ap.parse_args()

    if args.ani:
        interval, de_la = f"{args.ani}y", date.today() - timedelta(days=args.ani * 366)
        log(f"Umplere initiala: {args.ani} ani")
    else:
        interval, de_la = "1mo", date.today() - timedelta(days=args.zile + 10)
        log(f"Improspatare: ultimele {args.zile} zile")

    aur = cu_reincercari(lambda: aur_zilnic(interval), "AUR")
    log(f"  aur: {len(aur)} zile, {min(aur)} → {max(aur)}")

    valute = cu_reincercari(lambda: valute_zilnic(de_la, date.today()), "VALUTE")
    log(f"  valute: {len(valute)} zile")

    randuri = construieste(aur, valute)
    if args.ani is None:
        limita = (date.today() - timedelta(days=args.zile)).isoformat()
        randuri = [r for r in randuri if r["data"] >= limita]
    log(f"  {len(randuri)} randuri de scris")
    if randuri:
        p, u = randuri[0], randuri[-1]
        log(f"  primul: {p['data']}  {p['xau_usd']:,.2f} USD/oz → {p['ron_gram_24k']:,.2f} RON/g")
        log(f"  ultimul: {u['data']}  {u['xau_usd']:,.2f} USD/oz → {u['ron_gram_24k']:,.2f} RON/g")

    if args.test:
        log("MOD TEST — nu scriu in baza")
        return
    if randuri and salveaza(randuri):
        log(f"OK — {len(randuri)} randuri salvate in {TABEL}")
    elif randuri:
        sys.exit(1)


if __name__ == "__main__":
    main()
