"""Strutture dati e funzioni comuni."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Esclusioni automatiche per tipo di componente (PC completi, notebook...)
ESCLUSIONI_TIPO = {
    "gpu": [
        # PC completi e notebook
        r"\bpc\b", r"computer", r"workstation", r"desktop", r"\bryzen\b", r"\bi[3579][ -]?\d",
        r"intel core", r"\bultra [3579]\b", r"\b\d+\s?tb\b", r"\bssd\b", r"\bnvme\b",
        r"\b(32|64)\s?gb\b", r"notebook", r"portatil", r"laptop",
        # accessori che citano il modello della scheda
        r"\bwaterblock\b", r"\bdissipatore\b", r"riser", r"\bcavo\b", r"\bcable\b",
        r"adattatore", r"\bstaffa\b", r"anti-?sag", r"backplate",
    ],
    "ram": [],
    "cpu": [],
}


@dataclass
class Annuncio:
    """Annuncio di un usato (Subito, eBay, Vinted...)."""
    fonte: str
    id: str
    titolo: str
    prezzo: float
    spedizione: float | None      # None = solo ritiro / non indicata
    url: str
    luogo: str = ""
    descrizione: str = ""
    venditore: str = ""
    negozio: bool = False          # venditore professionale
    feedback: int | None = None    # numero feedback (eBay)
    feedback_pct: float | None = None
    condizione: str = ""

    @property
    def chiave(self) -> str:
        return f"{self.fonte}:{self.id}"

    @property
    def totale(self) -> float:
        return round(self.prezzo + (self.spedizione or 0), 2)


@dataclass
class Offerta:
    """Offerta di un negozio (prodotto nuovo)."""
    negozio: str
    titolo: str
    totale: float
    url: str
    stelle: float | None = None
    recensioni: int | None = None
    disponibile: bool = True
    extra: dict = field(default_factory=dict)


def euro(testo: str) -> float | None:
    """'1.234,56 €' -> 1234.56 · '1000' -> 1000 · '12.50' -> 12.5"""
    if testo is None:
        return None
    t = testo.replace("\xa0", " ")
    # 1) con punto delle migliaia: 1.234 / 1.234,56
    m = re.search(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?(?!\d)", t)
    if m:
        return float(m.group(0).replace(".", "").replace(",", "."))
    # 2) cifre semplici, con decimali a virgola o punto: 1000 / 1000,50 / 12.50
    m = re.search(r"\d+(?:[.,]\d{1,2}(?!\d))?", t)
    if not m:
        return None
    return float(m.group(0).replace(",", "."))


def fmt_euro(v: float | None) -> str:
    if v is None:
        return "n.d."
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


class HttpErrore(Exception):
    """Errore HTTP con codice di stato (status=None per errori di rete)."""

    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        self.status = status


try:  # imita la connessione di Chrome: riduce i blocchi anti-bot
    from curl_cffi import requests as _cffi
except ImportError:  # pragma: no cover
    _cffi = None


class Http:
    """Sessione HTTP con firma da browser, pause e ritentativi."""

    def __init__(self, pausa: float = 1.5):
        headers = {
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        }
        if _cffi is not None:
            self.s = _cffi.Session(impersonate="chrome")
            self.motore = "curl_cffi"
        else:
            self.s = requests.Session()
            headers["User-Agent"] = USER_AGENT
            self.motore = "requests"
        self.s.headers.update(headers)
        self.pausa = pausa
        self._ultima = 0.0

    def get(self, url: str, **kw):
        ultimo_err: Exception | None = None
        ritentato_403 = False
        for tentativo in range(3):
            attesa = self.pausa - (time.time() - self._ultima)
            if attesa > 0:
                time.sleep(attesa)
            try:
                r = self.s.get(url, timeout=25, **kw)
            except Exception as e:  # errore di rete: si ritenta
                ultimo_err = HttpErrore(f"errore di rete: {e}")
                time.sleep(3 * (tentativo + 1))
                continue
            finally:
                self._ultima = time.time()
            if r.status_code < 400:
                return r
            err = HttpErrore(f"HTTP {r.status_code} per {url}", r.status_code)
            if r.status_code in (429, 500, 502, 503, 504):
                ultimo_err = err
                time.sleep(3 * (tentativo + 1))
                continue
            if r.status_code == 403 and not ritentato_403:
                # spesso il primo accesso viene rifiutato e il secondo (con i cookie
                # ricevuti) passa: un solo nuovo tentativo, dopo una pausa più lunga
                ritentato_403 = True
                ultimo_err = err
                time.sleep(6)
                continue
            raise err  # altri 4xx (404...): inutile ritentare
        raise ultimo_err  # type: ignore[misc]

    def post(self, url: str, **kw):
        r = self.s.post(url, timeout=25, **kw)
        if r.status_code >= 400:
            raise HttpErrore(f"HTTP {r.status_code} per {url}: {r.text[:200]}", r.status_code)
        return r
