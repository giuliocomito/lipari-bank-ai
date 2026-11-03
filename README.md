# LipariBank AI

Il backend dell'assistente AI del LipariBank, costruito giornata per giornata nel
bootcamp Python AI. Il Giorno 1 ha posato la fondazione: un'applicazione FastAPI con una
sonda `/health`, una configurazione che si rifiuta di partire se manca qualcosa, e i
controlli di qualità che girano puliti. Il Giorno 2 ha aggiunto il contratto dell'API:
la categorizzazione di un movimento e l'importazione di un estratto CSV
([più sotto](#giorno-2-il-contratto-dellapi)).

## Cosa serve

- **uv** 0.5 o superiore — è lui a procurarsi Python 3.12, non serve installarlo a parte
  ([installazione](https://docs.astral.sh/uv/getting-started/installation/)).
- **Git**.

## Dalla cartella vuota alla sonda che risponde

```bash
git clone <indirizzo del repository> lipari-bank-ai
cd lipari-bank-ai
uv sync --locked                 # Python 3.12 e tutte le dipendenze, alle versioni del lockfile
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
# incolla il risultato in .env, nella riga JWT_SECRET=
uv run uvicorn src.main:app --reload
```

In un altro terminale (su Windows PowerShell scrivi `curl.exe`: `curl` da solo è un alias
di `Invoke-WebRequest` e risponde in un altro formato):

```bash
curl localhost:8000/health
# {"status":"UP", ..., "environment":"development","credentials":{"openai":false,"anthropic":false}}
```

La documentazione interattiva è su http://localhost:8000/docs.

## La configurazione

Tutte le variabili sono in [`.env.example`](.env.example), una riga commentata per
ciascuna. Due sono obbligatorie e il progetto non parte senza: `DATABASE_URL` e
`JWT_SECRET` (almeno 32 caratteri). Le chiavi del modello (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`) servono dal Giorno 4: oggi il progetto parte senza, e `/health`
dice se ci sono senza mai mostrarne il valore.

Se manca qualcosa, il processo si ferma subito, con codice 1, e dice quale variabile e
cosa ci va:

```text
Configurazione non valida: il progetto non parte.
  - DATABASE_URL: manca. Ci va la stringa di connessione, postgresql+asyncpg://utente:password@host:5432/nome.
Si scrive nel file .env (l'elenco completo sta in .env.example) o nell'ambiente.
```

## I controlli

```bash
uv run ruff check .        # lint
uv run ruff format .       # formattazione
uv run mypy src            # tipi, in strict
uv run pytest              # test
```

## Le prove di quello che non deve accadere

Fatte il 2 novembre 2026, a mano oltre che nei test:

| prova | cosa succede |
|---|---|
| tolgo `DATABASE_URL` e avvio | non parte, codice 1: «DATABASE_URL: manca. Ci va la stringa di connessione…» |
| `/health` senza chiave del modello | `"credentials":{"openai":false,"anthropic":false}`; il test verifica che né la chiave né un suo pezzo compaiano nella risposta |
| `MAX_TOKENS_PER_REQUEST=duemila` | non parte, codice 1: «MAX_TOKENS_PER_REQUEST: valore non valido (Input should be a valid integer…)» |

## La prova della ricostruzione

Il 2 novembre 2026: clone del repository in una cartella nuova, poi i comandi di questo
README nell'ordine, senza aggiungere niente a memoria. Per simulare una macchina che non
ha mai visto il progetto, con una cache di uv vuota e un'installazione di Python separata
(`UV_CACHE_DIR` e `UV_PYTHON_INSTALL_DIR` puntati a cartelle nuove), quindi con Python
3.12 e tutte le dipendenze scaricate da capo.

- **Tempo**: 16 secondi dal `git clone` alla prima risposta di `/health`. I comandi li ha
  lanciati uno script, quindi è il tempo della macchina; una persona che legge e incolla
  aggiunge il tempo di lettura.
- **Il primo punto in cui ci si blocca**: il `JWT_SECRET`. È l'unico passo che non è un
  comando da copiare: bisogna generare il segreto e incollarlo a mano nella riga giusta
  del `.env`. Se lo si salta, il progetto non parte e dice esattamente cosa manca.
- Su Windows PowerShell 5.1, `curl` va scritto `curl.exe` (vedi sopra).

## L'estensione del Giorno 1: l'esempio che non mente

[`tests/test_env_example.py`](tests/test_env_example.py) confronta le variabili che
`Settings` legge davvero con le righe di `.env.example`, e fallisce in tutti e due i
versi: un campo senza riga, o una riga che nessuno legge. I nomi non li ricostruisce
dal nome del campo in maiuscolo: li legge dalla configurazione, seguendo alias e
prefisso, e un secondo test lo dimostra su una configurazione con `env_prefix` e un alias.

- **Scelto**: il confronto automatico, perché il `.env.example` è la prima cosa che il
  collega in ferie legge, e un esempio che mente è peggio di nessun esempio.
- **Scartato**: generare `.env.example` da `Settings` con uno script: si rigenera solo
  se qualcuno si ricorda di lanciarlo, il test invece lo ricorda a ogni `pytest`.
- **Il numero**: 10 variabili confrontate su 10 righe, in 0,3 secondi; provato a togliere
  `DEFAULT_MODEL` dall'esempio e ad aggiungere una `REDIS_URL` orfana, e il test ha
  fallito tutte e due le volte nominando la variabile.

## Dove stanno le dipendenze di sviluppo

Nel **gruppo di sviluppo** `[dependency-groups] dev`, scritto da `uv add --dev`, non in
un extra opzionale `[project.optional-dependencies]`.

- Un gruppo di sviluppo non fa parte del pacchetto: non lo installa chi usa il progetto
  e non finisce nei metadati pubblicati, mentre un extra sì.
- `uv sync` lo installa da solo in sviluppo, e `uv sync --no-dev` lo esclude
  dall'immagine di produzione: il collega non deve ricordarsi `.[dev]`.
- È lo standard più recente (PEP 735, 2024); gli extra restano per le funzioni
  facoltative dell'applicazione, non per gli strumenti di chi sviluppa.

## La revisione del codice scritto con l'assistente

Giorno 1 in [`docs/ai-review/G1.md`](docs/ai-review/G1.md), Giorno 2 in
[`docs/ai-review/G2.md`](docs/ai-review/G2.md).

## Giorno 2: il contratto dell'API

L'ufficio Operations carica ogni mattina l'estratto dei movimenti, e qualche riga è
sbagliata. Da oggi l'API classifica un movimento, importa il file intero rendendo conto
di ogni riga, e riporta ogni errore nella stessa forma.

| endpoint | cosa fa |
|---|---|
| `POST /api/ai/categorize` | classifica un movimento (`description`, `amount` > 0, `currency` di tre lettere, EUR se manca) in una di sei categorie, con una `confidence` fra 0 e 1. Oggi decide una regola a parole chiave; dal Giorno 4 un modello, con lo stesso contratto |
| `POST /api/ai/movements/import` | un CSV (`multipart/form-data`, campo `file`, intestazione `date,description,amount,currency`, al massimo 2 MB): importa le righe valide e restituisce `imported_count` e `problems`, una voce per riga scartata con il suo numero nel file |
| `POST /api/ai/chat`, `POST /api/ai/glossary` | la chat (per ora un'eco) e il glossario interno |

Ogni errore, dal 404 al 500, ha la stessa busta: `timestamp`, `status`, `error` (il codice
stabile, per il programma), `message` (per una persona), `path`, `details` (per il 422,
un «campo: motivo» per campo). Il valore ricevuto non torna mai indietro, e un 500 non
contiene traceback né percorsi di file.

### Le nove prove

Con il server acceso (`uv run uvicorn src.main:app --reload`), dalla radice del progetto.
Fatte il 3 novembre 2026; l'esito è quello che si è visto.

```bash
# 1. la chat risponde
curl -X POST localhost:8000/api/ai/chat -H "Content-Type: application/json" -d '{"session_id":"s-1","message":"Ciao"}'
# 2. una bolletta è riconosciuta, con la sua confidenza
curl -X POST localhost:8000/api/ai/categorize -H "Content-Type: application/json" -d '{"description":"Bonifico Enel Energia","amount":87.40}'
# 3. il mio identificativo di richiesta torna uguale
curl -i localhost:8000/health -H "X-Request-Id: ops-2026-0042"
# 5. un corpo invalido dice quale campo, nella busta
curl -X POST localhost:8000/api/ai/categorize -H "Content-Type: application/json" -d '{"description":"Esselunga","amount":-5,"currency":"euro"}'
# 6. nessun traceback: rotta che non c'è, metodo sbagliato
curl localhost:8000/non-esiste ; curl localhost:8000/api/ai/glossary
# 7. il CSV da duecento righe, sette sbagliate
curl -X POST localhost:8000/api/ai/movements/import -F "file=@examples/estratto-200.csv"
# 8. e 9. un file vuoto, un file che non è un CSV
curl -X POST localhost:8000/api/ai/movements/import -F "file=@vuoto.csv"
curl -X POST localhost:8000/api/ai/movements/import -F "file=@immagine.png"
```

| # | prova | esito |
|---|---|---|
| 1 | la chat risponde | `"reply":"Echo: Ciao"` |
| 2 | la bolletta | `UTILITIES` / `ENERGY`, `confidence` 0.8, «Parola chiave «enel».» |
| 3 | il request-id | `X-Request-Id: ops-2026-0042`, lo stesso che ho mandato |
| 4 | la pagina nel browser | `client/index.html` servita su `http://localhost:5173` (`uv run python -m http.server 5173 --directory client`): «Classifica» risponde 200 con la categoria |
| 5 | corpo invalido | 422, `VALIDATION_ERROR`, `details`: `amount: Input should be greater than 0`, `currency: String should match pattern…` |
| 6 | niente traceback | 404 e 405 nella busta; un JSON rotto dà `corpo: JSON decode error`; nel log del server, zero traceback |
| 7 | 200 righe, 7 sbagliate | `imported_count` 193, `problems` alle righe 12, 37, 58, 91, 120, 154, 188, ognuna con il suo motivo |
| 8 | file vuoto | 422 `INVALID_FILE` «Il file è vuoto»; il server risponde ancora |
| 9 | file non CSV | 422 `INVALID_FILE` «Il file non è testo UTF-8: non è un CSV» |

La pagina va aperta su `localhost`, non su `127.0.0.1`: per il browser sono due origini
diverse, e la seconda non è nella lista del CORS. Il test
`test_cors_solo_per_le_origini_ammesse` lo verifica.

### La demo di due minuti

1. Server e pagina accesi, `/docs` aperto: i quattro endpoint, con gli esempi di risposta.
2. Carico `examples/estratto-200.csv`: 193 importate, sette righe segnalate. Apro il file
   alla riga 58 e c'è `euro` al posto di `EUR`, come dice il motivo.
3. Lo ricarico: stesso esito, con `replayed: true`. Il conto non raddoppia.
4. Dalla pagina nel browser, «Bonifico Enel Energia»: `UTILITIES`, confidenza 0.8.

### La decisione: le righe buone si importano, le sbagliate si dichiarano

Duecento righe, sette sbagliate: importo le 193 buone e restituisco le sette con il loro
numero di riga e il motivo.

- Chi carica è un ufficio che lavora un file al giorno. Rifiutare il file intero per una
  riga ferma 193 movimenti giusti in attesa di chi prepara il file, e la correzione passa
  da un altro sistema.
- La risposta gli dice cosa fare adesso: correggere solo quelle sette righe e caricarle.
  Il conto torna sempre, perché `imported_count` più le voci di `problems` fa il numero
  di righe di dati del file.
- Il rischio della scelta è una riga sbagliata che passa per buona. Lo coprono i test:
  dieci modi diversi di sporcare una riga, più le sette del file d'esempio, e nessuna
  risulta importata.

### L'estensione: l'importazione che si può rilanciare (la n. 3)

Lo stesso file caricato due volte non raddoppia il conto. La seconda volta torna l'esito
della prima, con `replayed: true`, e niente viene contato di nuovo.

- **Scelto**: «lo stesso file» è la chiave che il chiamante dichiara nell'header
  `Idempotency-Key`, come nei sistemi di pagamento. Se non la dichiara, è il contenuto,
  byte per byte (sha256). Con la chiave, la stessa chiave per un file diverso è un errore
  del chiamante: 409 `IDEMPOTENCY_KEY_REUSED`, nella busta.
- **Scartato**: il nome del file. Ogni mattina il file si chiama `estratto.csv`, quindi
  scartare per nome rifiuterebbe il file di domani. E se lo stesso file arriva rinominato,
  il nome lo farebbe passare due volte.
- **Come lo so**: [`tests/test_import_rilanciabile.py`](tests/test_import_rilanciabile.py)
  carica due volte `examples/estratto-200.csv` e il totale resta 193. Poi con una chiave:
  la stessa chiave e lo stesso file restituiscono la prima risposta, la stessa chiave con
  un altro file restituisce 409, e il totale non si muove.

Il registro sta in memoria finché non arriva il database (Giorno 3), e ricorda le ultime
mille importazioni. Lo riceve l'endpoint con `Depends(get_registro)`, ed è grazie a questo
che il test lo sostituisce con uno vuoto (`dependency_overrides`). I limiti sono nella
[revisione](docs/ai-review/G2.md).
