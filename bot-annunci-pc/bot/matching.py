"""Verifica che un titolo corrisponda davvero al prodotto cercato."""
from __future__ import annotations

import re

from .common import ESCLUSIONI_TIPO


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").lower())


def corrisponde(prodotto: dict, titolo: str) -> bool:
    t = _norm(titolo)
    for rx in prodotto.get("tutti", []):
        if not re.search(rx, t):
            return False
    esclusioni = list(prodotto.get("escludi", [])) + ESCLUSIONI_TIPO.get(prodotto.get("tipo", ""), [])
    for rx in esclusioni:
        if re.search(rx, t):
            return False
    if prodotto.get("cl_max"):
        cl = latenza_cl(t)
        if cl is not None and cl > prodotto["cl_max"]:
            return False
    return True


def latenza_cl(testo: str) -> int | None:
    m = re.search(r"\bc\s?l\s?-?(\d{2})\b", _norm(testo))
    return int(m.group(1)) if m else None


def da_scartare(testo: str, parole: list[str]) -> str | None:
    t = _norm(testo)
    for rx in parole:
        if re.search(rx, t):
            return rx
    return None


def segnali_sospetti(testo: str, parole: list[str]) -> list[str]:
    t = _norm(testo)
    trovati = []
    for rx in parole:
        m = re.search(rx, t)
        if m:
            trovati.append(m.group(0).strip())
    return trovati
