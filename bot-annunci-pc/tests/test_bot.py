"""Test offline: parser, matching, soglie e un giro completo simulato.
Esegui con:  python -m pytest -q   (oppure  python tests/test_bot.py)
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402

from bot import main as M  # noqa: E402
from bot.common import Annuncio, euro  # noqa: E402
from bot.matching import corrisponde, da_scartare  # noqa: E402
from bot.prezzi import calcola_riferimenti, valuta_usato  # noqa: E402
from bot.sources import ebay, subito, trovaprezzi  # noqa: E402
from bot.storico import Stato  # noqa: E402
from bot.telegram import Telegram  # noqa: E402

CFG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"))
PROD = {p["id"]: p for p in CFG["prodotti"]}


def subito_html(items):
    data = {"props": {"pageProps": {"initialState": {"items": {"originalList": items}}}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></html>'


def sub_item(i, titolo, prezzo, sped="0,99", body=""):
    feats = {"/price": {"values": [{"key": str(prezzo)}]}}
    if sped is not None:
        feats["/item_shippable"] = {"values": [{"key": "1"}]}
        feats["/item_shipping_cost_tuttosubito"] = {"values": [{"key": sped}]}
    feats["/item_condition"] = {"values": [{"key": "20", "value": "Come nuovo"}]}
    return {"kind": "AdItem", "urn": f"id:ad:x:list:{i}", "subject": titolo, "body": body,
            "features": feats, "advertiser": {"userId": "1", "company": False},
            "geo": {"town": {"value": "Roma"}, "city": {"shortName": "RM"}},
            "urls": {"default": f"https://www.subito.it/informatica/x-{i}.htm"}}


def tp_li(nome, negozio, tot, rate="rate45", rec="1.234"):
    return f'''<li class="listing_item clearfix"><div class="item_name_desc"><a class="item_name" href="/goto/1">{nome}</a></div>
    <span class="merchant_name">{negozio}</span>
    <a class="merchant_reviews rating_image {rate}" href="#"></a><a class="merchant_reviews" href="#">({rec})</a>
    <div class="item_price"><div class="item_basic_price">{tot}</div><div class="item_total_price"><span>Tot.</span> {tot}</div>
    <div class="item_availability">Disponibilità<span class="available"></span></div></div></li>'''


def test_euro():
    assert euro("1.234,56 €") == 1234.56
    assert euro("Tot. 700,88 €") == 700.88
    assert euro("750") == 750
    assert euro("1000") == 1000          # Subito: niente punto delle migliaia
    assert euro("1999 €") == 1999
    assert euro("1.008,99 €") == 1008.99
    assert euro("12.50") == 12.5
    assert euro("0,99") == 0.99
    assert euro("1.000") == 1000


def test_matching():
    g = PROD["rx9060xt16"]
    assert corrisponde(g, "Gigabyte Radeon RX 9060 XT GAMING Ice OC 16G")
    assert not corrisponde(g, "Sapphire Pulse RX 9060 XT 8GB")
    assert not corrisponde(g, "PC Gaming Ryzen 5 7600 RX 9060 XT")
    assert corrisponde(PROD["rx9070"], "PowerColor Reaper RX 9070 16GB")
    assert not corrisponde(PROD["rx9070"], "Sapphire RX 9070 XT Nitro+")
    assert not corrisponde(PROD["rx7900xt"], "RX 7900 XTX Merc")
    assert corrisponde(PROD["rtx4070tis"], "RTX 4070 Ti Super Asus TUF")
    assert not corrisponde(PROD["rtx4070tis"], "RTX 4070 Ti Asus TUF")
    r = PROD["ddr4_32_3600"]
    assert corrisponde(r, "Corsair Vengeance LPX 32GB (2x16) DDR4 3600 CL18")
    assert not corrisponde(r, "Kingston DDR4 32GB 2x16 3600 CL20")
    assert not corrisponde(r, "Sodimm DDR4 32GB 2x16 3600 portatile")
    c = PROD["r7_5700x3d"]
    assert corrisponde(c, "CPU AMD Ryzen 7 5700X3D")
    assert not corrisponde(c, "Bundle Ryzen 5700X3D + ASUS TUF Gaming B550M-Plus")
    assert not corrisponde(c, "AMD Ryzen 7 5700X processore 3,4 GHz")
    # casi reali (dry-run 20/11/2026): accessori e PC completi
    assert not corrisponde(PROD["rx7900xt"], "OEM Cavo riser PCIe 4.0 x16, flessibile a 180°, per schede grafiche RTX 4090, RX 7900 XT")
    assert not corrisponde(PROD["rtx5060ti16"], "ULTRA 7 270 PLUS - RTX 5060 TI - 32 GB - 1TB+256GB")
    assert not corrisponde(PROD["rtx5060ti16"], "Workstation compatta Ultra 7 265K RTX 5060 Ti 16GB")
    assert corrisponde(PROD["rtx5060ti16"], "ASUS Dual NVIDIA GeForce RTX 5060 Ti 16GB GDDR7 OC Edition")
    assert corrisponde(PROD["rtx5070ti"], "PNY VGA PNY GeForce RTX 5070TI 16GB Gaming Triple Fan ARGB")
    assert corrisponde(PROD["rx7900xt"], "XFX Radeon RX 7900XT - Scheda grafica da gioco con GDDR6 da 20 GB")
    assert da_scartare("RX 9060 XT guasta", CFG["scarta_se_contiene"])
    assert da_scartare("Cerco RX 9060 XT", CFG["scarta_se_contiene"])


def test_parser_subito():
    html = subito_html([sub_item(1, "RX 9060 XT 16G", 750), sub_item(2, "RX 9060 XT", 300, sped=None)])
    ads = subito.parse(html)
    assert len(ads) == 2 and ads[0].totale == 750.99 and ads[1].spedizione is None


def test_parser_trovaprezzi():
    html = "<ul>" + tp_li("ASUS Dual RX 9060 XT 16GB", "Eprice", "716,39 €") + \
           tp_li("XFX RX 9060XT 16GB", "Shop", "600,00 €", rate="rate20") + "</ul>"
    off = trovaprezzi.parse(html)
    assert off[0].totale == 716.39 and off[0].stelle == 4.5 and off[0].recensioni == 1234
    assert off[1].stelle == 2.0


def test_parser_ebay():
    data = {"itemSummaries": [{"itemId": "v1|1|0", "title": "RX 9060 XT 16GB", "price": {"value": "400.00", "currency": "EUR"},
                               "shippingOptions": [{"shippingCost": {"value": "9.90"}}],
                               "seller": {"username": "pippo", "feedbackScore": 3, "feedbackPercentage": "100.0"},
                               "itemWebUrl": "https://ebay.it/itm/1", "itemLocation": {"city": "Milano", "country": "IT"}}]}
    a = ebay.parse(data)[0]
    assert a.totale == 409.9 and a.feedback == 3


def test_soglie():
    R = CFG["regole"]
    rif = calcola_riferimenti(560, 550, 400, R)
    assert rif.tetto_usato == 385.0          # min(70% di 550, 400)
    rif2 = calcola_riferimenti(560, 550, 300, R)
    assert rif2.tetto_usato == 300           # mediana usato più bassa
    mk = lambda p: Annuncio("Subito", "1", "x", p, 0, "u")  # noqa: E731
    assert valuta_usato(mk(380), rif, R)[1].startswith("✅")
    assert valuta_usato(mk(390), rif, R)[0] is False
    assert valuta_usato(mk(300), rif, R)[1].startswith("🟡")   # 54%
    assert valuta_usato(mk(250), rif, R)[1].startswith("🔴")   # 45%
    solo_usato = calcola_riferimenti(None, None, 250, R)
    assert solo_usato.base == "usato" and valuta_usato(mk(240), solo_usato, R)[0]


def test_offerta_assurda_scartata():
    from bot.common import Offerta
    from bot.prezzi import migliore_offerta
    p = PROD["rx9070"]
    off = [Offerta("Kaufland", "RX 9070 16GB staffa?", 83.95, "u", 4.5, 300),
           Offerta("A", "PowerColor RX 9070 16GB", 800, "u", 4.5, 300),
           Offerta("B", "Sapphire RX 9070 16GB", 820, "u", 4.5, 300),
           Offerta("C", "ASUS RX 9070 16GB", 850, "u", 4.5, 300)]
    assert migliore_offerta(p, off, CFG["negozi"]).totale == 800


def test_mediana_usato_ignora_truffe():
    with tempfile.TemporaryDirectory() as d:
        st = Stato(Path(d) / "stato.json")
        for i, prezzo in enumerate([100, 110, 125, 140, 145, 410, 900, 950, 1000, 1050]):
            st.registra_usato("x", f"s:{i}", prezzo)
        assert st.mediana_usato("x", 30, 5) < 400                    # senza filtro: falsata
        assert st.mediana_usato("x", 30, 5, prezzo_min=725) is None   # 4 campioni validi < 5
        st.registra_usato("x", "s:99", 880)
        assert st.mediana_usato("x", 30, 5, prezzo_min=725) == 950


def test_giro_completo(monkeypatch=None):
    """Simula due esecuzioni: la prima avvisa, la seconda non ripete."""
    sub_page = subito_html([
        sub_item(10, "Sapphire Pulse RX 9060 XT 16GB", 380),
        sub_item(11, "RX 9060 XT 16GB come nuova", 250, body="pagamento con bonifico, scrivimi su whatsapp"),
        sub_item(12, "RX 9060 XT 16GB", 520),
        sub_item(13, "RX 9060 XT 8GB", 200),
        sub_item(14, "Cerco RX 9060 XT", 300),
    ])
    tp_page = "<ul>" + tp_li("ASUS Dual RX 9060 XT 16GB", "Eprice", "550,00 €") + \
              tp_li("RX 9060 XT 16GB", "eBay", "450,00 €") + "</ul>"
    subito.cerca = lambda http, q: subito.parse(sub_page)
    trovaprezzi.cerca = lambda http, url: trovaprezzi.parse(tp_page)
    cfg = dict(CFG)
    cfg["prodotti"] = [PROD["rx9060xt16"]]
    with tempfile.TemporaryDirectory() as d:
        stato = Stato(Path(d) / "stato.json")
        tg = Telegram(dry_run=True)
        run = M.Esecuzione(cfg, stato, tg)
        run.nuovo(cfg["prodotti"][0])
        run.usato(cfg["prodotti"][0])
        assert stato.nuovo_oggi("rx9060xt16") == 550.0     # eBay escluso
        assert tg.inviati == 2                              # 380 (✅) e 250 (🔴)
        stato.salva()
        stato2 = Stato(Path(d) / "stato.json")
        tg2 = Telegram(dry_run=True)
        run2 = M.Esecuzione(cfg, stato2, tg2)
        run2.usato(cfg["prodotti"][0])
        assert tg2.inviati == 0                             # già visti

    # budget: con tetto GPU a 300 € passa solo l'annuncio da 250 €
    cfg_b = dict(cfg, budget={"gpu": 300})
    with tempfile.TemporaryDirectory() as d:
        stato = Stato(Path(d) / "stato.json")
        tg = Telegram(dry_run=True)
        run = M.Esecuzione(cfg_b, stato, tg)
        assert run.budget(cfg["prodotti"][0]) == 300
        run.nuovo(cfg["prodotti"][0])
        run.usato(cfg["prodotti"][0])
        assert tg.inviati == 1
    assert M.Esecuzione(CFG, None, None).budget(PROD["r7_5800x3d"]) == 250
    assert M.Esecuzione(CFG, None, None).budget(PROD["ddr4_32_3200"]) == 180


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
