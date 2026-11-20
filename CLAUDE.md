# Bot annunci PC — contesto per Claude Code

Rispondi sempre in **italiano**, in modo conciso. Alessio non scrive codice per questo progetto: il codice lo scrivi tu, lui approva e testa.
Ambiente: Windows 11, PowerShell, repo in `C:\Workspace\bot-offerte-build-pc`. Git e Python 3.12 sono installati (winget).

## Cos'è
È un bot Python che cerca componenti PC usati e nuovi e manda avvisi su Telegram con un'etichetta anti-truffa.
Gira su **GitHub Actions** (repo `caronealessio/bot-offerte-build-pc`), workflow `.github/workflows/bot.yml`, ogni 30 min + avvio manuale (`workflow_dispatch`, input `modalita`: `normale` | `test-telegram`).
Lo storico (`data/stato.json`) viene committato dal workflow a ogni esecuzione.

## Struttura (attenzione: il codice è nella SOTTOCARTELLA `bot-annunci-pc/`)
```
.github/workflows/bot.yml       # usa defaults.run.working-directory: bot-annunci-pc
bot-annunci-pc/
  config.yaml                   # regole %, filtri negozi, parole da scartare/sospette, 13 prodotti
  requirements.txt              # requests, beautifulsoup4, PyYAML, curl_cffi
  bot/main.py                   # orchestrazione: nuovo() per Trovaprezzi, usato() per Subito/eBay, riepiloghi, salute fonti
  bot/common.py                 # Annuncio, Offerta, euro(), Http (curl_cffi impersonate="chrome", fallback requests), HttpErrore(status)
  bot/matching.py               # corrisponde() via regex tutti/escludi + esclusioni per tipo + cl_max RAM
  bot/prezzi.py                 # migliore_offerta, calcola_riferimenti, valuta_usato, segnali_venditore
  bot/storico.py                # Stato: visti, storico nuovo (min giornaliero), storico usato, avvisi, errori, meta
  bot/telegram.py               # sendMessage HTML; --dry-run stampa invece di inviare
  bot/sources/subito.py         # pagina pubblica di ricerca, dati in <script id="__NEXT_DATA__"> → props.pageProps.initialState.items.originalList
  bot/sources/trovaprezzi.py    # li.listing_item: .item_name, .merchant_name, .item_total_price, rating "rateXX", (n recensioni); 404 = nessuna offerta
  bot/sources/ebay.py           # API Browse ufficiale (EBAY_CLIENT_ID/SECRET, facoltative)
  tests/test_bot.py             # test offline: python tests\test_bot.py
  data/stato.json               # NON committare modifiche locali (lo gestisce il workflow)
```
Comandi (da `bot-annunci-pc/`): `pip install -r requirements.txt` · `python tests\test_bot.py` · `python -m bot.main --dry-run` · `python -m bot.main --test-telegram`

## Regole di prezzo decise con Alessio (non cambiarle senza chiedere)
- Nessun tetto fisso: decide solo la mediana.
- **Riferimento nuovo** = mediana a 30 giorni del prezzo minimo giornaliero su Trovaprezzi, spedizione inclusa. Negozi con ≥3,5★ e ≥30 recensioni, eBay escluso.
- **Tetto usato** = min(70% del riferimento nuovo, mediana a 30 giorni dell'usato). La mediana dell'usato vale solo con ≥5 campioni, outlier rimossi con IQR.
- Etichette usato: ✅ ≤ tetto · 🟡 50-60% del nuovo · 🔴 <50% = possibile truffa (si avvisa sempre).
- Nuovo: 📉 avviso se ≤90% della mediana a 30 giorni o se è il minimo storico (dopo 7 giorni di storico).
- Senza offerte del nuovo (5700X3D, RX 7900 GRE): riferimento = mediana dell'usato (🟡 <85%, 🔴 <75%).
- Segnali ⚠️: parole sospette nella descrizione (bonifico, whatsapp, telefono...), venditori eBay con <10 feedback o <97% di positivi, Subito "solo ritiro".
- Primo giro: massimo 3 avvisi per prodotto; poi 8. Riepilogo il lunedì. Avviso se una fonte fallisce 3 esecuzioni di fila.

## Prodotti (config.yaml)
GPU ≥16GB: RX 9060 XT 16GB (preferita), RX 9070, RX 9070 XT, RX 7800 XT, RX 7900 GRE, RX 7900 XT, RTX 5060 Ti 16GB, RTX 5070 Ti, RTX 4070 Ti Super.
RAM: DDR4 32GB 2x16 3600 CL≤18 e 3200 CL≤16 (no 4 banchi, no SO-DIMM).
CPU: Ryzen 7 5700X3D, 5800X3D (escludere bundle e PC completi).
PC di Alessio: AM4, B450M micro-ATX, PCIe 3.0, case Q300L (GPU max 360 mm), alimentatore 750W.

## Stato attuale (20/11/2026)
- Telegram funziona: secrets `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID` configurati su GitHub. **Non chiedere né scrivere mai token in file o commit.**
- Primo giro su GitHub: **403 Forbidden** su ogni richiesta a Subito e Trovaprezzi (anti-bot).
- Correzione in corso: `Http` è passato da `requests` a `curl_cffi` (imita la firma TLS di Chrome). Modifiche locali ancora da committare in `bot/common.py`, `bot/sources/trovaprezzi.py` e `requirements.txt`.
- La cartella `strumenti/` (script di auto-sync) non serve più: va eliminata.

## Piano
1. Commit e push di curl_cffi, poi test su GitHub.
2. Se su GitHub resta il 403 ma dal PC funziona → **piano A**: eseguire il bot in locale con l'Utilità di pianificazione di Windows (ogni 15-30 min, token in variabili d'ambiente utente o in un `.env` ignorato da git, `stato.json` locale), e disattivare lo schedule su GitHub. Chiedere conferma ad Alessio prima di farlo.
3. Poi: chiavi eBay (facoltative); fase 2 con Vinted, AliExpress e Idealo (anti-bot, best effort). Facebook Marketplace è escluso.

## Regole operative
- Prima di ogni commit esegui i test. Messaggi di commit in italiano.
- Non committare mai `data/stato.json` modificato in locale (ripristinalo con `git checkout -- bot-annunci-pc/data/stato.json`).
- Scraping educato: pause ≥1,5 s, niente login né bypass di CAPTCHA, solo pagine pubbliche e API ufficiali.
- Per lanciare e leggere il workflow usa la GitHub CLI (`gh workflow run bot.yml -f modalita=normale`, `gh run watch`, `gh run view --log`). Se non c'è: `winget install --id GitHub.cli -e`, poi `gh auth login` (lo fa Alessio).
