"""Subito.it: legge la pagina pubblica dei risultati (dati in __NEXT_DATA__)."""
from __future__ import annotations

import json
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from ..common import Annuncio, Http, euro

URL = "https://www.subito.it/annunci-italia/vendita/informatica/?q={q}&order=datedesc"


def _feature(item: dict, uri: str) -> str | None:
    f = (item.get("features") or {}).get(uri)
    if not f or not f.get("values"):
        return None
    return f["values"][0].get("key")


def parse(html: str) -> list[Annuncio]:
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        raise RuntimeError("Subito: struttura pagina cambiata o accesso bloccato (__NEXT_DATA__ assente)")
    data = json.loads(tag.string or tag.text)
    lista = data["props"]["pageProps"]["initialState"]["items"]["originalList"]
    out: list[Annuncio] = []
    for it in lista:
        if it.get("kind") != "AdItem":
            continue
        prezzo = euro(_feature(it, "/price") or "")
        if not prezzo:
            continue
        spedibile = _feature(it, "/item_shippable") == "1"
        sped = None
        if spedibile:
            sped = euro(_feature(it, "/item_shipping_cost_tuttosubito") or "") or 0.0
        urn = it.get("urn", "")
        ad_id = urn.rsplit(":", 1)[-1] if urn else it.get("urls", {}).get("default", "")
        geo = it.get("geo") or {}
        luogo = ", ".join(x for x in [
            (geo.get("town") or {}).get("value"),
            (geo.get("city") or {}).get("shortName"),
        ] if x)
        adv = it.get("advertiser") or {}
        cond = (it.get("features") or {}).get("/item_condition", {})
        cond_txt = cond.get("values", [{}])[0].get("value", "") if cond else ""
        out.append(Annuncio(
            fonte="Subito",
            id=str(ad_id),
            titolo=it.get("subject", ""),
            prezzo=prezzo,
            spedizione=sped,
            url=(it.get("urls") or {}).get("default", ""),
            luogo=luogo,
            descrizione=it.get("body", "") or "",
            venditore=str(adv.get("userId", "")),
            negozio=bool(adv.get("company")),
            condizione=cond_txt,
        ))
    return out


def cerca(http: Http, query: str) -> list[Annuncio]:
    r = http.get(URL.format(q=quote_plus(query)))
    return parse(r.text)
