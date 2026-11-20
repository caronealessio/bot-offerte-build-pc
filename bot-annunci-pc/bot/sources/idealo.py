"""Idealo.it: pagina pubblica di ricerca (risultati in JSON base64 dentro la pagina).

Serve per due cose:
- offerte dei negozi (seconda fonte del prezzo NUOVO, oltre a Trovaprezzi);
- offerte AliExpress elencate da Idealo (AliExpress da solo carica i prodotti con
  un'API interna firmata, che non usiamo).
"""
from __future__ import annotations

import base64
import json
import re
from urllib.parse import quote

from ..common import Annuncio, Http, Offerta, euro

URL = "https://www.idealo.it/risultati.html?q={q}"
MARKETPLACE = ("marketplace", "(mkp)")


def parse(html: str) -> list[dict]:
    m = re.search(r"initialData\['searchResult'\]\s*=\s*\"([^\"]+)\"", html)
    if not m:
        raise RuntimeError("Idealo: struttura pagina cambiata o accesso bloccato (searchResult assente)")
    return json.loads(base64.b64decode(m.group(1))).get("items", [])


def _prezzo(it: dict) -> tuple[float | None, float]:
    prezzo = it.get("rawPrice")
    if prezzo is None:
        prezzo = euro(((it.get("offerInfo") or {}).get("formattedPrice")) or "")
    sped = euro(((it.get("shopInfo") or {}).get("shippingCosts")) or "") or 0.0
    return (float(prezzo) if prezzo else None), sped


def _negozio(it: dict) -> str:
    return ((it.get("shopInfo") or {}).get("shopName") or "").strip()


def offerte(items: list[dict]) -> list[Offerta]:
    """Prodotti (non annunci sciolti) con il prezzo più basso tra i negozi, spedizione inclusa."""
    out = []
    for it in items:
        oi = it.get("offerInfo") or {}
        if it.get("type") != "PRODUCT" or oi.get("usedOnly"):
            continue
        # su Idealo non ci sono stelle/recensioni: i venditori dei marketplace non sono verificabili
        if any(x in _negozio(it).lower() for x in MARKETPLACE):
            continue
        prezzo, sped = _prezzo(it)
        if not prezzo:
            continue
        out.append(Offerta(
            negozio=_negozio(it) or "Idealo",
            titolo=it.get("title") or "",
            totale=round(prezzo + sped, 2),
            url=it.get("href") or oi.get("leadoutHref") or "",
            extra={"fonte": "Idealo", "offerte": oi.get("offerCount")},
        ))
    return out


def aliexpress(items: list[dict]) -> list[Annuncio]:
    """Offerte AliExpress trovate su Idealo, trattate come annunci (venditori da verificare)."""
    out = []
    for it in items:
        if "aliexpress" not in _negozio(it).lower():
            continue
        prezzo, sped = _prezzo(it)
        if not prezzo:
            continue
        oi = it.get("offerInfo") or {}
        out.append(Annuncio(
            fonte="AliExpress",
            id=str(it.get("offerId") or it.get("id") or ""),
            titolo=it.get("title") or "",
            prezzo=prezzo,
            spedizione=sped,
            url=oi.get("leadoutHref") or it.get("href") or "",
            negozio=True,
            condizione="Nuovo (via Idealo)",
        ))
    return out


def cerca(http: Http, query: str) -> list[dict]:
    r = http.get(URL.format(q=quote(query)))
    return parse(r.text)
