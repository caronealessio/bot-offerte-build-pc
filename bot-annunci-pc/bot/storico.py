"""Stato persistente (data/stato.json): annunci visti, storico prezzi, contatori errori."""
from __future__ import annotations

import json
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROMA = ZoneInfo("Europe/Rome")


def oggi() -> str:
    return datetime.now(ROMA).date().isoformat()


def ora_iso() -> str:
    return datetime.now(ROMA).isoformat(timespec="minutes")


class Stato:
    def __init__(self, path: Path):
        self.path = path
        if path.exists():
            self.d = json.loads(path.read_text(encoding="utf-8"))
        else:
            self.d = {}
        for k in ("visti", "nuovo", "usato", "avvisi_nuovo", "errori", "negozi_visti", "meta"):
            self.d.setdefault(k, {})

    # ---------- annunci già visti ----------
    def visto(self, chiave: str) -> bool:
        return chiave in self.d["visti"]

    def segna_visto(self, chiave: str, prezzo: float):
        self.d["visti"][chiave] = [oggi(), prezzo]

    def prezzo_visto(self, chiave: str) -> float | None:
        v = self.d["visti"].get(chiave)
        return v[1] if v else None

    # ---------- storico NUOVO (minimo giornaliero) ----------
    def registra_nuovo(self, pid: str, prezzo: float):
        st = self.d["nuovo"].setdefault(pid, {})
        g = oggi()
        st[g] = min(prezzo, st.get(g, prezzo))

    def nuovo_oggi(self, pid: str) -> float | None:
        return self.d["nuovo"].get(pid, {}).get(oggi())

    def mediana_nuovo(self, pid: str, giorni: int, escludi_oggi: bool = False) -> float | None:
        st = self.d["nuovo"].get(pid, {})
        lim = (date.fromisoformat(oggi()) - timedelta(days=giorni)).isoformat()
        vals = [v for g, v in st.items() if g >= lim and not (escludi_oggi and g == oggi())]
        return round(statistics.median(vals), 2) if vals else None

    def minimo_storico_nuovo(self, pid: str, escludi_oggi: bool = True) -> float | None:
        st = self.d["nuovo"].get(pid, {})
        vals = [v for g, v in st.items() if not (escludi_oggi and g == oggi())]
        return min(vals) if vals else None

    def giorni_storico_nuovo(self, pid: str) -> int:
        return len(self.d["nuovo"].get(pid, {}))

    # ---------- storico USATO (un prezzo per annuncio) ----------
    def registra_usato(self, pid: str, chiave: str, prezzo: float):
        st = self.d["usato"].setdefault(pid, {})
        if chiave not in st:
            st[chiave] = [oggi(), prezzo]

    def campioni_usato(self, pid: str, giorni: int, prezzo_min: float | None = None) -> list[float]:
        st = self.d["usato"].get(pid, {})
        lim = (date.fromisoformat(oggi()) - timedelta(days=giorni)).isoformat()
        return [p for g, p in st.values() if g >= lim and (prezzo_min is None or p >= prezzo_min)]

    def mediana_usato(self, pid: str, giorni: int, minimo: int,
                      prezzo_min: float | None = None) -> float | None:
        """prezzo_min: esclude i prezzi da "possibile truffa", che altrimenti
        abbassano la mediana (es. tanti annunci falsi a 100 € per una GPU da 1.400 €)."""
        vals = pulisci_outlier(self.campioni_usato(pid, giorni, prezzo_min))
        if len(vals) < minimo:
            return None
        return round(statistics.median(vals), 2)

    # ---------- avvisi sul nuovo (per non ripetersi) ----------
    def ultimo_avviso_nuovo(self, pid: str) -> float | None:
        v = self.d["avvisi_nuovo"].get(pid)
        if not v:
            return None
        g, prezzo = v
        # dopo 7 giorni si può avvisare di nuovo allo stesso prezzo
        if date.fromisoformat(g) < date.fromisoformat(oggi()) - timedelta(days=7):
            return None
        return prezzo

    def segna_avviso_nuovo(self, pid: str, prezzo: float):
        self.d["avvisi_nuovo"][pid] = [oggi(), prezzo]

    # ---------- negozi visti (per il riepilogo settimanale) ----------
    def registra_negozio(self, negozio: str):
        self.d["negozi_visti"][negozio] = oggi()

    # ---------- errori delle fonti ----------
    def errore(self, fonte: str) -> int:
        e = self.d["errori"].setdefault(fonte, {"consecutivi": 0, "avvisato": False})
        e["consecutivi"] += 1
        return e["consecutivi"]

    def ok(self, fonte: str) -> bool:
        """Azzera il contatore. Ritorna True se la fonte era in errore segnalato."""
        e = self.d["errori"].get(fonte)
        era_avvisato = bool(e and e.get("avvisato"))
        self.d["errori"][fonte] = {"consecutivi": 0, "avvisato": False}
        return era_avvisato

    # ---------- meta ----------
    def get_meta(self, k, default=None):
        return self.d["meta"].get(k, default)

    def set_meta(self, k, v):
        self.d["meta"][k] = v

    # ---------- salvataggio ----------
    def pulisci(self, giorni: int = 75):
        lim = (date.fromisoformat(oggi()) - timedelta(days=giorni)).isoformat()
        self.d["visti"] = {k: v for k, v in self.d["visti"].items() if v[0] >= lim}
        for pid, st in self.d["usato"].items():
            self.d["usato"][pid] = {k: v for k, v in st.items() if v[0] >= lim}
        lim_nuovo = (date.fromisoformat(oggi()) - timedelta(days=400)).isoformat()
        for pid, st in self.d["nuovo"].items():
            self.d["nuovo"][pid] = {g: v for g, v in st.items() if g >= lim_nuovo}

    def salva(self):
        self.pulisci()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def pulisci_outlier(vals: list[float]) -> list[float]:
    """Rimuove i valori anomali con il metodo IQR."""
    if len(vals) < 4:
        return list(vals)
    q = statistics.quantiles(vals, n=4)
    q1, q3 = q[0], q[2]
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [v for v in vals if lo <= v <= hi]
