"""Calcolo riferimenti, tetti ed etichette."""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from .common import Annuncio, Offerta
from .matching import corrisponde

# Un'offerta del nuovo sotto il 50% della mediana delle offerte valide è un errore
PREZZO_MIN_SU_MEDIANA_OFFERTE = 0.5


@dataclass
class Riferimenti:
    nuovo_oggi: float | None
    mediana_nuovo: float | None    # mediana 30 gg del minimo giornaliero
    mediana_usato: float | None    # mediana 30 gg degli annunci usati
    tetto_usato: float | None
    base: str                      # "nuovo" oppure "usato" (se manca il nuovo)

    @property
    def rif_nuovo(self) -> float | None:
        return self.mediana_nuovo or self.nuovo_oggi


def migliore_offerta(prodotto: dict, offerte: list[Offerta], cfg_negozi: dict) -> Offerta | None:
    escludi = {n.lower() for n in cfg_negozi.get("escludi", [])}
    valide = []
    for o in offerte:
        if not o.disponibile or o.negozio.lower() in escludi:
            continue
        if not corrisponde(prodotto, o.titolo):
            continue
        if o.stelle is not None and o.stelle < cfg_negozi.get("stelle_minime", 0):
            continue
        if o.recensioni is not None and o.recensioni < cfg_negozi.get("recensioni_minime", 0):
            continue
        valide.append(o)
    if len(valide) >= 3:
        # scarta prezzi assurdi (accessori o inserzioni sbagliate sfuggiti al filtro)
        med = statistics.median(o.totale for o in valide)
        valide = [o for o in valide if o.totale >= med * PREZZO_MIN_SU_MEDIANA_OFFERTE]
    return min(valide, key=lambda o: o.totale) if valide else None


def calcola_riferimenti(nuovo_oggi, mediana_nuovo, mediana_usato, regole) -> Riferimenti:
    rif = mediana_nuovo or nuovo_oggi
    if rif:
        tetto = rif * regole["usato_max_su_nuovo"]
        if mediana_usato:
            tetto = min(tetto, mediana_usato)
        return Riferimenti(nuovo_oggi, mediana_nuovo, mediana_usato, round(tetto, 2), "nuovo")
    if mediana_usato:
        # Nuovo non disponibile (es. CPU fuori produzione): si usa solo l'usato
        return Riferimenti(nuovo_oggi, mediana_nuovo, mediana_usato, mediana_usato, "usato")
    return Riferimenti(nuovo_oggi, mediana_nuovo, mediana_usato, None, "nessuno")


def valuta_usato(a: Annuncio, rif: Riferimenti, regole: dict) -> tuple[bool, str, float | None]:
    """Ritorna (da_avvisare, etichetta, rapporto_sul_nuovo)."""
    tot = a.totale
    if rif.base == "nuovo":
        r = tot / rif.rif_nuovo
        if r < regole["soglia_truffa"]:
            return True, "🔴 POSSIBILE TRUFFA", r
        if r < regole["soglia_affare"]:
            return True, "🟡 Affare, da verificare", r
        if tot <= rif.tetto_usato:
            return True, "✅ Buon prezzo", r
        return False, "", r
    if rif.base == "usato":
        # 50%/60% del nuovo ≈ 75%/85% della mediana dell'usato
        r = tot / rif.mediana_usato
        if r < 0.75:
            return True, "🔴 POSSIBILE TRUFFA (rispetto all'usato)", None
        if r < 0.85:
            return True, "🟡 Affare, da verificare (rispetto all'usato)", None
        if tot <= rif.tetto_usato:
            return True, "✅ Sotto la mediana dell'usato", None
        return False, "", None
    return False, "", None


def segnali_venditore(a: Annuncio) -> list[str]:
    s = []
    if a.feedback is not None and a.feedback < 10:
        s.append(f"venditore con pochi feedback ({a.feedback})")
    if a.feedback_pct is not None and a.feedback_pct < 97:
        s.append(f"feedback positivi solo {a.feedback_pct:.1f}%")
    if a.fonte == "Subito" and a.spedizione is None:
        s.append("solo ritiro di persona (nessuna spedizione TuttoSubito)")
    return s
