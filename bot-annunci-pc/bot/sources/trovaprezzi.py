"""Trovaprezzi.it: offerte dei negozi (prodotto nuovo), ordinate per prezzo totale."""
from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..common import Http, HttpErrore, Offerta, euro

BASE = "https://www.trovaprezzi.it"


def parse(html: str) -> list[Offerta]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Offerta] = []
    for li in soup.select("li.listing_item"):
        nome = li.select_one(".item_name")
        negozio = li.select_one(".merchant_name")
        tot = li.select_one(".item_total_price")
        base = li.select_one(".item_basic_price")
        if not (nome and negozio and (tot or base)):
            continue
        totale = euro(tot.get_text(" ", strip=True)) if tot else None
        if totale is None and base:
            totale = euro(base.get_text(" ", strip=True))
            sped = li.select_one(".item_delivery_price")
            if sped and "gratuita" not in sped.get_text().lower():
                totale = (totale or 0) + (euro(sped.get_text()) or 0)
        if not totale:
            continue
        stelle = None
        rating = li.select_one(".merchant_reviews.rating_image")
        if rating:
            m = re.search(r"rate(\d{2})", " ".join(rating.get("class", [])))
            if m:
                stelle = int(m.group(1)) / 10
        recensioni = None
        for a in li.select("a.merchant_reviews"):
            m = re.search(r"\(([\d.]+)\)", a.get_text())
            if m:
                recensioni = int(m.group(1).replace(".", ""))
        disp = li.select_one(".item_availability span")
        disponibile = True
        if disp is not None:
            cls = " ".join(disp.get("class", []))
            disponibile = "not_available" not in cls and "unavailable" not in cls
        href = nome.get("href") or ""
        out.append(Offerta(
            negozio=negozio.get_text(strip=True),
            titolo=nome.get_text(" ", strip=True),
            totale=round(totale, 2),
            url=urljoin(BASE, href),
            stelle=stelle,
            recensioni=recensioni,
            disponibile=disponibile,
        ))
    return out


def cerca(http: Http, url: str) -> list[Offerta]:
    try:
        r = http.get(url)
    except HttpErrore as e:
        # 404 = nessuna offerta per quel prodotto (es. fuori produzione): non è un errore
        if e.status == 404:
            return []
        raise
    return parse(r.text)
