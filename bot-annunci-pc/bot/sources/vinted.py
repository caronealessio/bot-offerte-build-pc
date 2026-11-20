"""Vinted.it: pagina pubblica di ricerca (dati Next.js in self.__next_f.push)."""
from __future__ import annotations

import json
import re
from urllib.parse import quote, urljoin

from ..common import Annuncio, Http, euro

BASE = "https://www.vinted.it"
URL = BASE + "/catalog?search_text={q}&order=newest_first"


def _flight(html: str) -> str:
    parti = []
    for c in re.findall(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.S):
        try:
            j = json.loads(c)
        except ValueError:
            continue
        if len(j) > 1 and isinstance(j[1], str):
            parti.append(j[1])
    return "".join(parti)


def _importo(v) -> float | None:
    if isinstance(v, dict):
        v = v.get("amount")
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return euro(str(v))


def parse(html: str) -> list[Annuncio]:
    flight = _flight(html)
    if not flight:
        raise RuntimeError("Vinted: struttura pagina cambiata o accesso bloccato (dati Next.js assenti)")
    dec = json.JSONDecoder()
    out: dict[str, Annuncio] = {}
    for m in re.finditer(r'"productItem":\s*\{', flight):
        try:
            it, _ = dec.raw_decode(flight, m.end() - 1)
        except ValueError:
            continue
        iid = str(it.get("id") or "")
        titolo = it.get("title") or ""
        # prezzo totale = prezzo + protezione acquisti (spedizione esclusa)
        prezzo = _importo(it.get("totalItemPrice")) or _importo(it.get("price"))
        if not (iid and titolo and prezzo) or iid in out:
            continue
        box = it.get("itemBox") or {}
        cond = box.get("secondLine") if isinstance(box.get("secondLine"), str) else ""
        out[iid] = Annuncio(
            fonte="Vinted",
            id=iid,
            titolo=titolo,
            prezzo=prezzo,
            spedizione=0.0,  # non indicata nella ricerca: si paga a parte
            url=urljoin(BASE, it.get("url") or f"/items/{iid}"),
            negozio=bool((it.get("user") or {}).get("isBusiness")),
            venditore=str((it.get("user") or {}).get("id", "")),
            condizione=cond,
        )
    return list(out.values())


def cerca(http: Http, query: str) -> list[Annuncio]:
    r = http.get(URL.format(q=quote(query)))
    return parse(r.text)
