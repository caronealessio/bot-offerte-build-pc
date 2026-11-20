"""Bot annunci PC: cerca usato e nuovo, avvisa su Telegram.

Uso:
    python -m bot.main                 # esecuzione normale
    python -m bot.main --dry-run       # stampa i messaggi invece di inviarli
    python -m bot.main --test-telegram # invia solo un messaggio di prova
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml

from .common import Annuncio, Http, fmt_euro
from .matching import corrisponde, da_scartare, segnali_sospetti
from .prezzi import calcola_riferimenti, migliore_offerta, segnali_venditore, valuta_usato
from .sources import ebay, subito, trovaprezzi
from .storico import ROMA, Stato, oggi, ora_iso
from .telegram import Telegram, esc

ROOT = Path(__file__).resolve().parent.parent
MAX_AVVISI_PER_PRODOTTO = 8
MAX_AVVISI_PRIMO_GIRO = 3
SOGLIA_ERRORI = 3  # esecuzioni consecutive fallite prima di avvisare


class Esecuzione:
    def __init__(self, cfg: dict, stato: Stato, tg: Telegram):
        self.cfg = cfg
        self.stato = stato
        self.tg = tg
        self.http = Http()
        self.regole = cfg["regole"]
        self.esiti: dict[str, list[bool]] = {}  # fonte -> esiti delle richieste
        self.errori_txt: dict[str, str] = {}

    # ------------------------------------------------------------------
    def _esito(self, fonte: str, ok: bool, err: str = ""):
        self.esiti.setdefault(fonte, []).append(ok)
        if not ok:
            self.errori_txt[fonte] = err

    def _deve_aggiornare_nuovo(self, pid: str) -> bool:
        ultimo = self.stato.get_meta(f"nuovo_ts_{pid}")
        if not ultimo:
            return True
        ore = (datetime.now(ROMA) - datetime.fromisoformat(ultimo)).total_seconds() / 3600
        return ore >= self.cfg["frequenze"]["nuovo_ogni_ore"] - 0.1

    # ------------------------------------------------------------------
    def nuovo(self, p: dict):
        pid = p["id"]
        if not p.get("trovaprezzi") or not self._deve_aggiornare_nuovo(pid):
            return
        try:
            offerte = trovaprezzi.cerca(self.http, p["trovaprezzi"])
            self._esito("Trovaprezzi", True)
        except Exception as e:  # noqa: BLE001
            self._esito("Trovaprezzi", False, str(e))
            print(f"[{pid}] Trovaprezzi errore: {e}")
            return
        self.stato.set_meta(f"nuovo_ts_{pid}", ora_iso())
        best = migliore_offerta(p, offerte, self.cfg["negozi"])
        for o in offerte:
            if corrisponde(p, o.titolo):
                self.stato.registra_negozio(o.negozio)
        if not best:
            print(f"[{pid}] nessuna offerta valida sul nuovo")
            return
        med_prec = self.stato.mediana_nuovo(pid, self.regole["giorni_mediana"], escludi_oggi=True)
        min_storico = self.stato.minimo_storico_nuovo(pid)
        giorni = self.stato.giorni_storico_nuovo(pid)
        self.stato.registra_nuovo(pid, best.totale)
        print(f"[{pid}] nuovo: {best.totale} € da {best.negozio}")

        motivo = None
        if med_prec and best.totale <= med_prec * self.regole["nuovo_calo"]:
            motivo = f"-{(1 - best.totale / med_prec) * 100:.0f}% rispetto alla mediana a 30 giorni ({fmt_euro(med_prec)})"
        elif (min_storico and giorni >= self.regole["min_giorni_storico_nuovo"]
              and best.totale < min_storico):
            motivo = f"nuovo minimo storico (prima: {fmt_euro(min_storico)})"
        if not motivo:
            return
        ultimo = self.stato.ultimo_avviso_nuovo(pid)
        if ultimo is not None and best.totale >= ultimo:
            return
        stelle = f" · ⭐ {best.stelle:.1f}" if best.stelle else ""
        rec = f" ({best.recensioni} recensioni)" if best.recensioni else ""
        self.tg.invia(
            f"📉 <b>Calo di prezzo sul NUOVO — {esc(p['nome'])}</b>\n"
            f"{esc(best.titolo[:150])}\n"
            f"💶 <b>{fmt_euro(best.totale)}</b> spedizione inclusa\n"
            f"🏪 {esc(best.negozio)}{stelle}{rec}\n"
            f"📊 {esc(motivo)}\n"
            f"🔗 <a href=\"{esc(best.url)}\">Vai all'offerta</a>"
        )
        self.stato.segna_avviso_nuovo(pid, best.totale)

    # ------------------------------------------------------------------
    def _raccogli_usato(self, p: dict) -> list[Annuncio]:
        trovati: dict[str, Annuncio] = {}
        for q in p.get("subito", []):
            try:
                for a in subito.cerca(self.http, q):
                    trovati[a.chiave] = a
                self._esito("Subito", True)
            except Exception as e:  # noqa: BLE001
                self._esito("Subito", False, str(e))
                print(f"[{p['id']}] Subito errore ({q}): {e}")
        if p.get("ebay") and ebay.configurato():
            try:
                for a in ebay.cerca(self.http, p["ebay"]):
                    trovati[a.chiave] = a
                self._esito("eBay", True)
            except Exception as e:  # noqa: BLE001
                self._esito("eBay", False, str(e))
                print(f"[{p['id']}] eBay errore: {e}")
        return list(trovati.values())

    def riferimenti(self, pid: str):
        """Riferimenti di prezzo; la mediana dell'usato ignora i prezzi da truffa."""
        g = self.regole["giorni_mediana"]
        nuovo_oggi = self.stato.nuovo_oggi(pid)
        med_nuovo = self.stato.mediana_nuovo(pid, g)
        pavimento = self._pavimento_usato(pid)
        return calcola_riferimenti(
            nuovo_oggi, med_nuovo,
            self.stato.mediana_usato(pid, g, self.regole["min_campioni_usato"], pavimento),
            self.regole,
        )

    def _pavimento_usato(self, pid: str) -> float | None:
        rif_nuovo = self.stato.mediana_nuovo(pid, self.regole["giorni_mediana"]) or self.stato.nuovo_oggi(pid)
        return rif_nuovo * self.regole["soglia_truffa"] if rif_nuovo else None

    def usato(self, p: dict):
        pid = p["id"]
        primo_giro = not self.stato.get_meta(f"init_{pid}")
        pavimento = self._pavimento_usato(pid)
        annunci = []
        for a in self._raccogli_usato(p):
            if not corrisponde(p, a.titolo):
                continue
            if da_scartare(a.titolo + " " + a.descrizione, self.cfg["scarta_se_contiene"]):
                continue
            if a.prezzo < 20:  # prezzi simbolici ("1 €", "trattabile")
                continue
            annunci.append(a)
            if pavimento is None or a.totale >= pavimento:  # le truffe non entrano nella mediana
                self.stato.registra_usato(pid, a.chiave, a.totale)

        rif = self.riferimenti(pid)

        da_inviare = []
        for a in annunci:
            prec = self.stato.prezzo_visto(a.chiave)
            ribasso = None
            if prec is not None:
                if a.totale > prec * 0.95:
                    continue
                ribasso = prec
            self.stato.segna_visto(a.chiave, a.totale)
            avvisa, etichetta, rapporto = valuta_usato(a, rif, self.regole)
            if avvisa:
                da_inviare.append((a, etichetta, rapporto, ribasso))

        da_inviare.sort(key=lambda x: x[0].totale)
        limite = MAX_AVVISI_PRIMO_GIRO if primo_giro else MAX_AVVISI_PER_PRODOTTO
        for a, etichetta, rapporto, ribasso in da_inviare[:limite]:
            self.tg.invia(self._msg_usato(p, a, etichetta, rapporto, ribasso, rif))
        if len(da_inviare) > limite:
            self.tg.invia(f"ℹ️ {esc(p['nome'])}: altri {len(da_inviare) - limite} annunci sotto soglia non mostrati.")
        self.stato.set_meta(f"init_{pid}", oggi())
        print(f"[{pid}] usato: {len(annunci)} annunci validi, {len(da_inviare)} avvisi, tetto {rif.tetto_usato}")

    def _msg_usato(self, p, a: Annuncio, etichetta, rapporto, ribasso, rif) -> str:
        if a.spedizione is None:
            prezzo = f"<b>{fmt_euro(a.prezzo)}</b> (solo ritiro)"
        elif a.spedizione == 0:
            prezzo = f"<b>{fmt_euro(a.prezzo)}</b> + spedizione gratuita/non indicata"
        else:
            prezzo = f"{fmt_euro(a.prezzo)} + sped. {fmt_euro(a.spedizione)} = <b>{fmt_euro(a.totale)}</b>"
        if rapporto is not None:
            prezzo += f" ({rapporto * 100:.0f}% del nuovo)"
        righe = [f"{etichetta} — <b>{esc(p['nome'])}</b>"]
        if ribasso:
            righe.append(f"📉 Ribassato: prima {fmt_euro(ribasso)}")
        righe.append(esc(a.titolo[:150]))
        righe.append(f"💶 {prezzo}")
        info = " · ".join(x for x in [a.luogo, a.fonte, a.condizione, "negozio" if a.negozio else ""] if x)
        righe.append(f"📍 {esc(info)}")
        if a.fonte == "eBay" and a.venditore:
            fb = f" ({a.feedback} feedback, {a.feedback_pct:.1f}%)" if a.feedback is not None and a.feedback_pct is not None else ""
            righe.append(f"👤 {esc(a.venditore)}{fb}")
        rif_txt = []
        if rif.nuovo_oggi:
            rif_txt.append(f"nuovo oggi {fmt_euro(rif.nuovo_oggi)}")
        if rif.mediana_nuovo:
            rif_txt.append(f"mediana nuovo {fmt_euro(rif.mediana_nuovo)}")
        if rif.mediana_usato:
            rif_txt.append(f"mediana usato {fmt_euro(rif.mediana_usato)}")
        if rif.tetto_usato:
            rif_txt.append(f"tetto {fmt_euro(rif.tetto_usato)}")
        if rif_txt:
            righe.append("📊 " + " · ".join(rif_txt))
        segnali = segnali_sospetti(a.titolo + " " + a.descrizione, self.cfg["sospetto_se_contiene"])
        segnali += segnali_venditore(a)
        if segnali:
            righe.append("⚠️ Segnali: " + esc(", ".join(dict.fromkeys(segnali))))
        if "TRUFFA" in etichetta:
            righe.append("🛡️ Paga solo con il pagamento interno della piattaforma o con PayPal \"beni e servizi\". "
                         "Prima chiedi una foto con un foglio con nome e data.")
        righe.append(f"🔗 <a href=\"{esc(a.url)}\">Apri l'annuncio</a>")
        return "\n".join(righe)

    # ------------------------------------------------------------------
    def controlla_fonti(self):
        for fonte, esiti in self.esiti.items():
            if any(esiti):
                if self.stato.ok(fonte):
                    self.tg.invia(f"✅ {fonte} è tornato a funzionare.")
                continue
            n = self.stato.errore(fonte)
            e = self.stato.d["errori"][fonte]
            if n >= SOGLIA_ERRORI and not e.get("avvisato"):
                self.tg.invia(
                    f"⚠️ <b>{fonte} non risponde</b> da {n} esecuzioni consecutive.\n"
                    f"Errore: <code>{esc(self.errori_txt.get(fonte, '')[:300])}</code>\n"
                    f"Probabile blocco temporaneo o modifica del sito."
                )
                e["avvisato"] = True

    def riepilogo(self, iniziale: bool = False):
        titolo = "🤖 <b>Bot attivo!</b> Riferimenti di partenza:" if iniziale else "🗓️ <b>Riepilogo settimanale</b>"
        righe = [titolo, ""]
        for p in self.cfg["prodotti"]:
            rif = self.riferimenti(p["id"])
            righe.append(
                f"<b>{esc(p['nome'])}</b>: nuovo {fmt_euro(rif.nuovo_oggi)} · "
                f"mediana nuovo {fmt_euro(rif.mediana_nuovo)} · mediana usato {fmt_euro(rif.mediana_usato)} · "
                f"tetto usato <b>{fmt_euro(rif.tetto_usato)}</b>"
            )
        if not iniziale:
            negozi = sorted(self.stato.d["negozi_visti"])
            if negozi:
                righe += ["", f"🏪 Negozi trovati ({len(negozi)}): " + esc(", ".join(negozi))]
        else:
            righe += ["", "La mediana dell'usato diventa affidabile dopo qualche giorno di raccolta dati."]
        self.tg.invia("\n".join(righe))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--test-telegram", action="store_true")
    args = ap.parse_args(argv)

    tg = Telegram(dry_run=args.dry_run)
    if args.test_telegram:
        tg.invia("✅ Test riuscito: il bot annunci PC riesce a scriverti su Telegram.")
        return 0

    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    stato = Stato(ROOT / "data" / "stato.json")
    run = Esecuzione(cfg, stato, tg)
    primo_avvio = not stato.get_meta("primo_avvio")

    for p in cfg["prodotti"]:
        try:
            run.nuovo(p)
            run.usato(p)
        except Exception:  # noqa: BLE001
            traceback.print_exc()

    run.controlla_fonti()

    adesso = datetime.now(ROMA)
    if primo_avvio:
        run.riepilogo(iniziale=True)
        stato.set_meta("primo_avvio", oggi())
    elif adesso.weekday() == 0 and adesso.hour >= 8 and stato.get_meta("ultimo_riepilogo") != oggi():
        run.riepilogo()
        stato.set_meta("ultimo_riepilogo", oggi())

    stato.set_meta("ultima_esecuzione", ora_iso())
    stato.salva()
    print(f"Fatto. Messaggi inviati: {tg.inviati}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
