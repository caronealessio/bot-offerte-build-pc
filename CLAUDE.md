# Bot annunci PC — contesto per Claude Code

Rispondi sempre in **italiano**, in modo conciso. Alessio non scrive codice per questo progetto: il codice lo scrivi tu, lui approva e testa.
Ambiente: Windows 11, PowerShell, repo in `C:\Workspace\bot-offerte-build-pc`. Installati con winget: Git, Python 3.12 (`%LOCALAPPDATA%\Programs\Python\Python312\python.exe`, non sempre nel PATH dei terminali aperti prima), GitHub CLI (`C:\Program Files\GitHub CLI\gh.exe`, autenticata).

## Cos'è
È un bot Python che cerca componenti PC usati e nuovi e manda avvisi su Telegram con un'etichetta anti-truffa.
**Gira sul PC di Alessio** con l'Utilità di pianificazione: attività `Bot annunci PC`, ogni 30 min, lancia `esegui-bot.ps1` (log in `logs/`, 14 giorni). Token in `.env` nella radice del repo (ignorato da git, modello in `.env.example`); senza token lo script non parte.
Motivo: Trovaprezzi risponde 403 agli IP di GitHub Actions anche con curl_cffi (Subito invece funziona da GitHub).
Il workflow `.github/workflows/bot.yml` (repo `caronealessio/bot-offerte-build-pc`) è rimasto solo con avvio manuale (`workflow_dispatch`, `modalita`: `normale` | `test-telegram`), senza storico persistente.
Prossimo passo: spostare il bot su un **Raspberry Pi** (Linux, cron ogni 30 min, stesso `.env`).

## Struttura (attenzione: il codice è nella SOTTOCARTELLA `bot-annunci-pc/`)
```
esegui-bot.ps1                  # lanciatore per l'Utilità di pianificazione (accetta --dry-run)
.env / .env.example             # TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, EBAY_* (letti da main.carica_env)
.github/workflows/bot.yml       # solo manuale; defaults.run.working-directory: bot-annunci-pc
bot-annunci-pc/
  config.yaml                   # regole %, filtri negozi, parole da scartare/sospette, 13 prodotti
  requirements.txt              # requests, beautifulsoup4, PyYAML, curl_cffi, tzdata
  bot/main.py                   # orchestrazione: nuovo() per Trovaprezzi, usato() per Subito/eBay, riepiloghi, salute fonti
  bot/common.py                 # Annuncio, Offerta, euro(), Http (curl_cffi impersonate="chrome", 1 ritentativo su 403), esclusioni GPU (PC completi, accessori)
  bot/matching.py               # corrisponde() via regex tutti/escludi + esclusioni per tipo + cl_max RAM
  bot/prezzi.py                 # migliore_offerta (scarta offerte <50% della mediana offerte), calcola_riferimenti, valuta_usato
  bot/storico.py                # Stato: visti, storico nuovo, storico usato, avvisi, errori, meta; VERSIONE_DATI per migrazioni
  bot/telegram.py               # sendMessage HTML; --dry-run stampa invece di inviare
  bot/sources/subito.py         # __NEXT_DATA__ → props.pageProps.initialState.items.originalList; prezzo "/price" SENZA punto migliaia ("1000")
  bot/sources/trovaprezzi.py    # li.listing_item ...; 404 = nessuna offerta
  bot/sources/vinted.py         # usato: pagina /catalog (Next.js self.__next_f.push → "productItem"); internazionale (FR/DE/ES)
  bot/sources/idealo.py         # nuovo (2ª fonte, niente marketplace) + offerte AliExpress: /risultati.html, JSON base64 in initialData['searchResult']
  bot/sources/ebay.py           # API Browse ufficiale (EBAY_CLIENT_ID/SECRET, facoltative)
  tests/test_bot.py             # test offline: python tests\test_bot.py
  data/stato.json               # SOLO LOCALE (ignorato da git): non va più su GitHub
```
Comandi (da `bot-annunci-pc/`): `pip install -r requirements.txt` · `python tests\test_bot.py` · `python -m bot.main --dry-run` · `python -m bot.main --test-telegram`
Il `--dry-run` modifica comunque `data/stato.json`: fai una copia prima e ripristinala dopo.

## Regole di prezzo decise con Alessio (non cambiarle senza chiedere)
- **Budget massimo** (deciso il 20/11/2026, `budget:` in config.yaml, spedizione inclusa): GPU 500 €, CPU 250 €, RAM 180 €. Sopra il budget non si avvisa mai (né usato né nuovo). Sotto il budget le etichette restano decise dalle mediane.
- **Riferimento nuovo** = mediana a 30 giorni del prezzo minimo giornaliero tra Trovaprezzi e Idealo, spedizione inclusa. Trovaprezzi: negozi con ≥3,5★ e ≥30 recensioni. Idealo (niente recensioni): esclusi i marketplace. eBay e AliExpress esclusi.
- Annunci sotto il 15% del nuovo ignorati (scatole, cavi, accessori). AliExpress passa come "annuncio" ma non entra nella mediana dell'usato.
- **Tetto usato** = min(70% del riferimento nuovo, mediana a 30 giorni dell'usato). La mediana dell'usato vale solo con ≥5 campioni, outlier rimossi con IQR, ed esclude i prezzi sotto il 50% del nuovo (truffe).
- Etichette usato: ✅ ≤ tetto · 🟡 50-60% del nuovo · 🔴 <50% = possibile truffa (si avvisa sempre).
- Nuovo: 📉 avviso se ≤90% della mediana a 30 giorni o se è il minimo storico (dopo 7 giorni di storico).
- Senza offerte del nuovo (5700X3D, RX 7900 GRE): riferimento = mediana dell'usato (🟡 <85%, 🔴 <75%).
- Segnali ⚠️: parole sospette nella descrizione (bonifico, whatsapp, telefono...), venditori eBay con <10 feedback o <97% di positivi, Subito "solo ritiro".
- Primo giro: massimo 3 avvisi per prodotto; poi 8. Riepilogo il lunedì. Avviso se una fonte fallisce 3 esecuzioni di fila.
- Questione aperta: per GPU fuori produzione (RTX 4070 Ti Super, RX 7900 XT) il nuovo su Trovaprezzi è gonfiato (Marketplace) e l'usato normale esce 🔴. Proposto di usare solo la mediana dell'usato: in attesa di decisione di Alessio.

## Prodotti (config.yaml)
GPU ≥16GB: RX 9060 XT 16GB (preferita), RX 9070, RX 9070 XT, RX 7800 XT, RX 7900 GRE, RX 7900 XT, RTX 5060 Ti 16GB, RTX 5070 Ti, RTX 4070 Ti Super.
RAM: DDR4 32GB 2x16 3600 CL≤18 e 3200 CL≤16 (no 4 banchi, no SO-DIMM).
CPU: Ryzen 7 5700X3D, 5800X3D (escludere bundle e PC completi).
PC di Alessio: AM4, B450M micro-ATX, PCIe 3.0, case Q300L (GPU max 360 mm), alimentatore 750W.

## Piano
1. ✅ curl_cffi, correzioni matching/prezzi, esecuzione locale con l'Utilità di pianificazione.
2. Raspberry Pi: installare Python + requirements, copiare `.env` e `data/stato.json`, cron ogni 30 min; poi disattivare l'attività Windows.
3. ✅ Vinted, Idealo, AliExpress (solo tramite Idealo: la pagina AliExpress carica i prodotti con un'API firmata, non la usiamo).
4. Chiavi eBay (facoltative, le crea Alessio). Facebook Marketplace è escluso (richiede login).

## Regole operative
- Prima di ogni commit esegui i test. Messaggi di commit in italiano.
- **Non chiedere né scrivere mai token in file o commit**: il `.env` lo compila Alessio.
- Scraping educato: pause ≥1,5 s, niente login né bypass di CAPTCHA, solo pagine pubbliche e API ufficiali.
- GitHub CLI: `gh workflow run bot.yml -f modalita=normale`, `gh run watch`, `gh run view --log`.
