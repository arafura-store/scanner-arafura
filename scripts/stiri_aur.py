#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STIRI CARE MISCA AURUL — aduce titluri din Google News si le pune in Supabase.

De ce pe categorii si nu "stiri despre aur": pretul aurului nu se misca doar de
la stirile despre aur. Se misca de la dobanzile Fed, de la inflatia americana si
de la dolar. De multe ori stirea care conteaza nu contine deloc cuvantul "gold".

Browserul nu poate cere direct fluxurile RSS (fara antete CORS), deci le aducem
aici si pagina citeste din Supabase — acelasi tipar ca la restul aplicatiei.

Rulare:
    python scripts/stiri_aur.py            # aduce si salveaza
    python scripts/stiri_aur.py --test     # doar afiseaza
"""

import os, re, sys, json, html, time, hashlib, argparse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import urllib.request, urllib.error, urllib.parse

SUPABASE_URL = "https://bxsfzfnpejkmwxkuoshb.supabase.co/rest/v1"
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or "sb_publishable_naQ6WD91NngRNjTlV5fSJw_BInIyurw"
TABEL = "stiri_aur"

# Ce cautam, si sub ce eticheta. Ordinea conteaza: prima potrivire castiga.
SURSE = [
    ("aur",      "gold price"),
    ("fed",      "Federal Reserve interest rate decision"),
    ("inflatie", "US inflation CPI report"),
    ("dolar",    "US dollar index DXY"),
    ("banci",    "central banks buying gold reserves"),
]
MAX_PER_CATEGORIE = 12
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def http(url, metoda="GET", date_=None, headere=None, timeout=45):
    h = {"User-Agent": UA}
    if headere:
        h.update(headere)
    corp = None
    if date_ is not None:
        corp = json.dumps(date_, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json; charset=utf-8")
    req = urllib.request.Request(url, data=corp, headers=h, method=metoda)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def normalizeaza(titlu):
    """Cheie de dedublare: acelasi articol apare sub mai multe cautari."""
    t = re.sub(r"[^a-z0-9 ]", "", titlu.lower())
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t.encode()).hexdigest()[:24]


def ia_categoria(categorie, interogare):
    url = ("https://news.google.com/rss/search?q="
           + urllib.parse.quote(interogare) + "&hl=en-US&gl=US&ceid=US:en")
    st, corp = http(url)
    if st != 200:
        log(f"  {categorie}: HTTP {st}")
        return []
    try:
        rad = ET.fromstring(corp)
    except ET.ParseError as e:
        log(f"  {categorie}: XML invalid ({e})")
        return []

    randuri = []
    for it in rad.findall(".//item")[:MAX_PER_CATEGORIE]:
        titlu = html.unescape(it.findtext("title", "") or "").strip()
        if not titlu:
            continue
        # fluxurile mai scapa si intrari de umplutura ("Videos", "Live Blog", indexuri)
        if len(re.sub(r"[^A-Za-z]", "", titlu.split(" - ")[0])) < 18:
            continue
        # Google adauga " - Sursa" la finalul titlului
        m = re.match(r"^(.*) - ([^-]{2,40})$", titlu)
        curat, sursa = (m.group(1).strip(), m.group(2).strip()) if m else (titlu, None)

        pub = None
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate", "")).astimezone(timezone.utc).isoformat()
        except Exception:
            pass

        randuri.append({
            "cheie": normalizeaza(curat),
            "titlu": curat[:400],
            "sursa": (sursa or "")[:80] or None,
            "link": (it.findtext("link", "") or "")[:900],
            "publicat_la": pub,
            "categorie": categorie,
        })
    return randuri


def salveaza(randuri):
    url = f"{SUPABASE_URL}/{TABEL}?on_conflict=cheie"
    h = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
         "Prefer": "resolution=merge-duplicates,return=minimal"}
    st, corp = http(url, "POST", randuri, h)
    if st in (200, 201, 204):
        return True
    log(f"  EROARE salvare: HTTP {st} {corp[:250]}")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    args = ap.parse_args()

    toate, vazute = [], set()
    for categorie, interogare in SURSE:
        r = ia_categoria(categorie, interogare)
        noi = [x for x in r if x["cheie"] not in vazute]
        for x in noi:
            vazute.add(x["cheie"])
        toate += noi
        log(f"  {categorie:<9} {len(r):>3} titluri, {len(noi):>3} noi")
        time.sleep(0.5)

    log(f"{len(toate)} stiri distincte")
    if args.test:
        for x in toate[:12]:
            print(f"   [{x['categorie']:<8}] {x['titlu'][:78]}  ({x['sursa']})")
        log("MOD TEST — nu salvez")
        return
    if toate and salveaza(toate):
        log(f"OK — {len(toate)} salvate in {TABEL}")
    elif toate:
        sys.exit(1)


if __name__ == "__main__":
    main()
