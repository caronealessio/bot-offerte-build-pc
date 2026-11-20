# Bot annunci PC: guida all'installazione

Servono circa 15 minuti e non devi scrivere codice.

---

## 1. Crea il bot Telegram

1. Su Telegram cerca **@BotFather** e premi **Avvia**.
2. Scrivi `/newbot`, scegli un nome (es. *Annunci PC Alessio*) e uno username che finisca con `bot` (es. `annunci_pc_alessio_bot`).
3. BotFather ti risponde con un **token** del tipo `123456789:AAH...`. Copialo e **non condividerlo con nessuno**.
4. Apri il tuo nuovo bot e premi **Avvia**. Questo passaggio serve: senza, il bot non può scriverti.
5. Cerca **@userinfobot**, premi **Avvia** e copia il numero accanto a **Id**: è il tuo **chat ID**.

## 2. Crea il repository su GitHub

1. Accedi a <https://github.com> (crea un account gratuito se non ce l'hai).
2. In alto a destra clicca **+**, poi **New repository**.
   - Nome: `bot-annunci-pc`
   - Visibilità: scegli in base alla tabella qui sotto.
   - Clicca **Create repository**.

| Visibilità | Minuti gratuiti | Frequenza consigliata |
|---|---|---|
| **Public** | illimitati | ogni 30 minuti (impostazione predefinita) |
| **Private** | 2000 al mese | ogni ora: nel file `.github/workflows/bot.yml` sostituisci `*/30 * * * *` con `0 * * * *` |

Il token e le chiavi restano protetti in entrambi i casi, perché stanno nei "Secrets" e non nei file. Con un repository pubblico sono visibili solo la configurazione e lo storico dei prezzi.

3. Nella pagina del repository vuoto clicca **uploading an existing file**.
4. Estrai lo zip sul PC e trascina nella pagina **tutto il contenuto** della cartella `bot-annunci-pc`, compresa la cartella `.github`.
   > Se la cartella `.github` non si vede, in Esplora file attiva *Visualizza → Elementi nascosti*.
5. Clicca **Commit changes**.

Per verificare: nel repository devi vedere le cartelle `.github`, `bot`, `data` e `tests` e il file `config.yaml`.

## 3. Inserisci i Secrets (token e chat ID)

1. Nel repository vai su **Settings → Secrets and variables → Actions**.
2. Clicca **New repository secret** e crea:

| Name | Valore |
|---|---|
| `TELEGRAM_TOKEN` | il token di BotFather |
| `TELEGRAM_CHAT_ID` | il numero di @userinfobot |

## 4. Dai al bot il permesso di salvare lo storico

**Settings → Actions → General**, poi in fondo alla pagina, sotto *Workflow permissions*, seleziona **Read and write permissions** e clicca **Save**.

## 5. Primo test

1. Apri il tab **Actions**. Se lo chiede, clicca **I understand my workflows, go ahead and enable them**.
2. A sinistra clicca **Bot annunci PC**, poi **Run workflow**. Nel campo scrivi `test-telegram` e clicca **Run workflow**.
3. Entro un minuto ti arriva su Telegram: *"✅ Test riuscito..."*.
4. Rilancia con **Run workflow** lasciando `normale`. Ti arriverà il messaggio **"🤖 Bot attivo!"** con i prezzi di riferimento di partenza.

Da quel momento il bot parte da solo.

## 6. eBay (facoltativo, si può fare in seguito)

1. Registrati su <https://developer.ebay.com> e crea una *Application* con chiavi **Production**.
2. Copia **App ID (Client ID)** e **Cert ID (Client Secret)**.
3. Aggiungili nei Secrets come `EBAY_CLIENT_ID` e `EBAY_CLIENT_SECRET`.

Senza queste chiavi il bot salta eBay e continua con le altre fonti.

---

## Come funziona

| Cosa | Come |
|---|---|
| Usato | Subito.it ed eBay.it (Italia, "Compralo subito") |
| Nuovo | Trovaprezzi.it (Amazon, BPM Power, ePrice e gli altri negozi), riletto ogni 2 ore. Sono esclusi i negozi con meno di 3,5 stelle o meno di 30 recensioni, ed eBay |
| Riferimento nuovo | Mediana a 30 giorni del prezzo minimo giornaliero, spedizione inclusa |
| Tetto usato | Il più basso tra il 70% del riferimento nuovo e la mediana a 30 giorni dell'usato |
| ✅ Buon prezzo | Usato sotto il tetto |
| 🟡 Affare | Usato tra il 50% e il 60% del nuovo |
| 🔴 Possibile truffa | Usato sotto il 50% del nuovo |
| ⚠️ Segnali | Parole sospette nella descrizione (bonifico, WhatsApp, numeri di telefono...) e venditori eBay con pochi feedback |
| 📉 Nuovo | Prezzo almeno il 10% sotto la mediana a 30 giorni, oppure nuovo minimo storico |
| 🗓️ Riepilogo | Ogni lunedì: riferimenti di tutti i prodotti e negozi trovati |
| Prodotto fuori produzione | Se non c'è il nuovo (es. 5700X3D, 7900 GRE), il bot usa come riferimento la mediana dell'usato |

Se una fonte smette di rispondere per 3 esecuzioni di fila, il bot ti avvisa.

## Modifiche frequenti (dal sito, senza codice)

Apri `config.yaml`, clicca l'icona della **matita**, modifica e poi clicca **Commit changes**.

- **Percentuali**: sezione `regole`.
- **Togliere un prodotto**: cancella il suo blocco, dalla riga `- id:` fino a quello successivo.
- **Parole da scartare o sospette**: liste `scarta_se_contiene` e `sospetto_se_contiene`.

## Problemi comuni

| Problema | Soluzione |
|---|---|
| Nessun messaggio dopo il test | Hai premuto **Avvia** sul tuo bot? Chat ID e token sono corretti? |
| Errore "Permission denied" nel passo "Salva lo storico" | Rivedi il punto 4 |
| Avviso "Subito non risponde" | Subito potrebbe bloccare i server di GitHub: scrivimelo e valutiamo un'alternativa |
| L'esecuzione parte con qualche minuto di ritardo | È normale: GitHub ritarda le esecuzioni programmate nei momenti di traffico |
