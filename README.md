# LipariBank AI

Il backend dell'assistente AI del LipariBank, costruito giornata per giornata nel
bootcamp Python AI. Il Giorno 1 ha posato la fondazione: un'applicazione FastAPI con una
sonda `/health`, una configurazione che si rifiuta di partire se manca qualcosa, e i
controlli di qualità che girano puliti. Il Giorno 2 ha aggiunto il contratto dell'API:
la categorizzazione di un movimento e l'importazione di un estratto CSV
([più sotto](#giorno-2-il-contratto-dellapi)). Il Giorno 3 gli ha dato una memoria: un
database PostgreSQL, la conversazione che sopravvive al riavvio, i conti e i movimenti
della banca ([più sotto](#giorno-3-la-memoria)). Il Giorno 4 lo fa rispondere con un
modello linguistico, Claude di Anthropic, con il costo di ogni risposta e un tetto di spesa
([più sotto](#giorno-4-il-modello-risponde)).

## Il repository e le giornate

Il progetto è un unico repository che cresce un giorno alla volta. Per vedere il codice
com'era alla consegna di una giornata c'è un'etichetta (*tag*) per ogni giorno: `g1`,
`g2`, `g3`. Per esempio `git checkout g2` riporta il progetto alla fine del Giorno 2, e
su GitHub la stessa etichetta si sceglie dal menu dei branch. Dal Giorno 4 il lavoro di
ogni giornata si sviluppa su un branch `giorno-N` e arriva su `main` con una pull request:
la pull request mostra in una pagina tutto quello che quella giornata ha cambiato.

I messaggi di commit seguono la convenzione
[Conventional Commits](https://www.conventionalcommits.org/it/v1.0.0/): un prefisso dice
il tipo di modifica (`feat` una funzionalità, `fix` una correzione, `docs` la
documentazione, `test` i test, `style` la formattazione) e fra parentesi il giorno, per
esempio `feat(g3): movimento e saldo insieme`.

Prima della pubblicazione, il 16 novembre 2026, gli otto commit dei primi tre giorni sono
stati riscritti per adottare questa convenzione e sostituire l'email dell'autore con
l'indirizzo anonimo di GitHub. Il contenuto dei file è identico, ma i codici dei commit
sono cambiati. Le consegne dei Giorni 1-3 citano i codici vecchi: questa è la
corrispondenza.

| Codice citato nelle consegne | Codice attuale | Commit |
|---|---|---|
| `fb0d28e` | `d5b7226` | feat(g1): setup del progetto |
| `9487394` | `8af6262` | docs(g1): README per un estraneo, .env.example verificato, revisione |
| `51883b8` | `05efc1f` | style(g1): test dell'esempio, riga troppo lunga riformattata da ruff |
| `1ea0b8c` | `8de5429` | docs(g1): README, la prova della ricostruzione cronometrata — tag `g1` |
| `55f5df6` | `e659d1a` | feat(g2): contratti Pydantic, router, errori in una busta, middleware |
| `6da257d` | `8e53eee` | feat(g2): import rilanciabile, limite di 2 MB, prove, decisione e revisione — tag `g2` |
| `dd629bb` | `18d9dc9` | feat(g3): PostgreSQL in Docker, modelli SQLAlchemy 2.0, migration Alembic, repository |
| `74352ab` | `630ac54` | feat(g3): movimento e saldo insieme, prove, decisione sul commit e revisione — tag `g3` |

## Cosa serve

- **uv** 0.5 o superiore — è lui a procurarsi Python 3.12, non serve installarlo a parte
  ([installazione](https://docs.astral.sh/uv/getting-started/installation/)).
- **Git**.
- **Docker** con Compose (Docker Desktop su Windows e macOS), acceso: dal Giorno 3 il
  database gira in un container.

## Dalla cartella vuota alla sonda che risponde

```bash
git clone <indirizzo del repository> lipari-bank-ai
cd lipari-bank-ai
uv sync --locked                 # Python 3.12 e tutte le dipendenze, alle versioni del lockfile
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
# incolla il risultato in .env, nella riga JWT_SECRET=
docker compose up -d             # PostgreSQL 16 con pgvector, sulla porta 5432
uv run alembic upgrade head      # lo schema, dalle migration: mai a mano
uv run python -m scripts.seed_accounts   # due clienti, tre conti, quaranta movimenti
docker compose exec postgres createdb -U lipari lipari_ai_test   # il database dei test, una volta
uv run uvicorn src.main:app --reload
```

Se sulla macchina c'è già un PostgreSQL, la porta 5432 è occupata e l'errore sembra di
credenziali (`password authentication failed for user "lipari"`): in `docker-compose.yml`
scrivi `"5433:5432"` e, nel `.env`, `localhost:5433`.

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
`ANTHROPIC_API_KEY`) servono dal Giorno 4 solo per parlare con un modello vero: il progetto
parte anche senza, la chat risponde 503 dicendo quale chiave manca, e `/health` dice se ci
sono senza mai mostrarne il valore. I test e le prove non ne hanno bisogno.

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
uv run mypy src scripts    # tipi, in strict
uv run pytest              # test: dal Giorno 3 parlano con il database lipari_ai_test
```

I test non toccano mai il database su cui lavori: `conftest.py` impone `lipari_ai_test`
(si cambia solo con `TEST_DATABASE_URL`) e a ogni esecuzione ricostruisce lo schema dalle
migration, da zero.

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
[`docs/ai-review/G2.md`](docs/ai-review/G2.md), Giorno 3 in
[`docs/ai-review/G3.md`](docs/ai-review/G3.md).

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

## Giorno 3: la memoria

Fino a ieri il servizio rispondeva e dimenticava tutto al riavvio. Da oggi c'è un database
PostgreSQL 16 (con pgvector, per il Giorno 5) in un container, lo schema ci arriva dalle
migration Alembic in [`alembic/versions/`](alembic/versions/), la conversazione resta, e
ci sono i dati su cui rispondere: clienti, conti e movimenti, popolati da
[`scripts/seed_accounts.py`](scripts/seed_accounts.py). Le query stanno tutte in
[`src/db/repos.py`](src/db/repos.py), l'unico file che sa che esiste un database.

| endpoint | cosa fa |
|---|---|
| `POST /api/ai/chat` | con `session_id` `"new"` apre una conversazione e la salva; con l'id di una conversazione dell'utente che chiede la continua; altrimenti 404 `CHAT_SESSION_NOT_FOUND` |
| `GET /api/ai/accounts/{iban}/movements` | i movimenti fra `date_from` e `date_to`, ognuno con l'intestatario (`owner`), da una JOIN movimento → conto → cliente |
| `GET /api/ai/accounts/{iban}/spending` | le uscite del periodo, mese per mese, e il totale; gli importi escono come stringhe (`"20402.22"`), perché un importo non passa da un float |
| `POST /api/ai/accounts/{iban}/movements` | l'estensione: registra un movimento e aggiorna il saldo, insieme o per niente; 201 con il saldo nuovo |

Ogni lettura dei conti è filtrata nella query per il portafoglio dell'operatore, che oggi
è finto (`mbianchi`, dal Giorno 6 arriva dal token). Il conto di un cliente di un altro
portafoglio risponde come un conto che non esiste: stesso 404 `ACCOUNT_NOT_FOUND`,
nessun nome. Dal Giorno 3 la chat vuole `"new"` o una conversazione esistente: la prova 1
del Giorno 2, con `"s-1"`, oggi risponde 404.

### Le prove

Fatte il 5 novembre 2026, dalla radice del progetto, con Docker acceso; l'esito è quello
che si è visto.

| prova | comando | esito |
|---|---|---|
| la migration da zero, e due volte | `docker compose down -v`, `docker compose up -d`, `uv run alembic upgrade head` due volte | 15 secondi dal volume cancellato allo schema completo. La prima `upgrade` applica le due migration, la seconda non fa niente; `alembic current` dà `508f6dff712c (head)`, e ci sono sei tabelle. Il database dei test se ne va con il volume: si ricrea con `docker compose exec postgres createdb -U lipari lipari_ai_test` |
| il centesimo | `uv run pytest tests/test_pw_g3.py -k centesimo` | Al seed si aggiungono 60 commissioni (0.10, 0.20, 0.30, 0.01) e quattro importi a tre decimali scritti dall'ORM, e il totale dell'endpoint coincide al centesimo con la somma fatta a mano. Gli stessi importi del seed, accumulati in virgola mobile, danno `20402.220000000016`; l'endpoint dà `"20402.22"` |
| i tre decimali | stessa prova | Il database li arrotonda mentre li scrive, senza dirlo: 12.345 diventa 12.35 e -0.005 diventa -0.01. **Decisione**: dall'API non arrivano. `MovementIn` accetta al massimo due decimali e rifiuta lo zero, con un 422 nella busta prima del database: un importo che cambia per strada, in una banca, è un errore, non un arrotondamento |
| la conversazione lunga | `uv run pytest tests/test_pw_g3.py -k cresce` | Una `POST /chat` fa 4 istruzioni SQL con 2 messaggi precedenti e 4 con 200. Caricando i messaggi a mano, conversazione per conversazione, 10 conversazioni costavano 11 query; con `selectinload` 2 |
| l'interruzione a metà | `uv run python -m scripts.prova_interruzione` | Il server gira in un processo a parte, con una pausa fra le due scritture, e viene ucciso durante la pausa. Per la chat e per il movimento: a metà il database mostra la transazione aperta con l'`INSERT` già fatto, invisibile da fuori; il client non riceve risposta; dopo, il database è identico a prima (`ESITO: niente a metà`) |
| il riavvio | `uv run uvicorn src.main:app`, una chat, il processo fermato e riavviato, la stessa `session_id` | La conversazione riprende: nel database ci sono i quattro messaggi, due prima e due dopo il riavvio |

Tutto insieme: `uv run pytest` dà 39 test verdi, 10 dal Code Blueprint e 5 del Project Work.

### La demo di due minuti

```bash
uv run uvicorn src.main:app --reload
AL=$(uv run python -c "import datetime as d; print(d.date.today())")
DAL=$(uv run python -c "import datetime as d; print(d.date.today() - d.timedelta(days=90))")
# 1. il trimestre di Paolo Ferri: le uscite mese per mese, e il totale al centesimo
curl "localhost:8000/api/ai/accounts/IT60X0542811101000000123/spending?date_from=$DAL&date_to=$AL"
# 2. i suoi movimenti, ognuno con l'intestatario: 35, tutti "owner":"Paolo Ferri"
curl "localhost:8000/api/ai/accounts/IT60X0542811101000000123/movements?date_from=$DAL&date_to=$AL"
# 3. il conto di Anna Greco, che è nel portafoglio di un collega: 404, e nessun nome
curl "localhost:8000/api/ai/accounts/IT60X0542811101000000789/spending?date_from=$DAL&date_to=$AL"
# 4. una conversazione, il server fermato (Ctrl+C) e riacceso, la stessa conversazione ripresa
curl -X POST localhost:8000/api/ai/chat -H "Content-Type: application/json" -d '{"session_id":"new","message":"Ciao"}'
curl -X POST localhost:8000/api/ai/chat -H "Content-Type: application/json" -d '{"session_id":"<quello di prima>","message":"Ci sei ancora?"}'
docker compose exec postgres psql -U lipari -d lipari_ai -c "SELECT role, content FROM chat_messages ORDER BY created_at;"
```

### La decisione: chi chiude la transazione

- **Chi decide che il lavoro è finito**: il service, con un `commit()` alla fine
  dell'operazione (`ChatService.chat`, `AccountService.post_movement`). Chi legge il service
  vede dove il lavoro finisce, e un service chiamato fuori da una richiesta HTTP (il seed,
  uno script, l'agente dei giorni dopo) si porta dietro la sua transazione.
- **Chi se ne accorge se la conferma fallisce**: il client. Il commit avviene prima che
  esista una risposta, quindi riceve un 500 nella busta e non un 201
  (`test_un_commit_che_fallisce_arriva_al_client`).
- **Scartato**: il commit in `get_db`, dopo lo `yield`. Misurato in
  `test_l_alternativa_scartata_il_commit_dopo_lo_yield`: con lo scope di default il client
  riceve 200 per una riga mai scritta. Con `scope="function"` riceve 500, ma ogni service
  dipenderebbe da una dipendenza HTTP per chiudere il proprio lavoro.

### L'estensione: il movimento che aggiorna il saldo (la n. 2)

`POST /api/ai/accounts/{iban}/movements` scrive in due tabelle, `movements` e il saldo in
`accounts`, e deve riuscire o fallire per intero.

- **Scelto**: un service che usa due repository, nessuno dei quali fa commit, e un solo
  commit alla fine. Il saldo si aggiorna dentro il database, in un'istruzione:
  `UPDATE accounts SET balance = balance + :importo RETURNING balance`, senza leggerlo
  prima.
- **Scartato**: il commit in ciascun repository, perché se il saldo fallisce il movimento
  resta scritto da solo e il conto non torna, senza nessun errore. E il «leggi il saldo,
  somma in Python, riscrivi», perché due richieste insieme leggono lo stesso saldo.
- **Come lo so**: `test_movimento_e_saldo_insieme_o_per_niente`
  (`uv run pytest tests/test_pw_g3.py -k insieme`) fa fallire il saldo dopo che il
  movimento è già stato scritto: 500, e movimenti e saldo restano quelli di prima. Con un
  commit messo apposta nel repository, il test fallisce. E 20 movimenti contemporanei da
  -1.00 su un saldo di 100.00 danno 80.00 con l'`UPDATE`, ma 99.00 con
  leggi-somma-riscrivi: 19 aggiornamenti persi, e nessun errore.

Il saldo può diventare negativo: il fido è una regola di dominio che oggi non c'è. I
limiti misurati (la storia della chat caricata tutta, i movimenti senza paginazione) sono
nella [revisione](docs/ai-review/G3.md).

## Giorno 4: il modello risponde

Da questa giornata l'assistente risponde con un modello linguistico. Il modello predefinito
è **Claude Opus 5.5** di Anthropic; OpenAI resta come seconda implementazione dello stesso
contratto. Cinque cose sono nuove.

- **Due fornitori dietro un'unica interfaccia.** `LLMProvider` ([`src/llm/client.py`](src/llm/client.py))
  è un `Protocol`: dice che un modello deve saper rispondere per intero (`complete`) e a
  pezzi (`stream`). Due adattatori traducono nel formato di Anthropic e di OpenAI, e una
  factory sceglie quale usare dal nome del modello in `DEFAULT_MODEL`.
- **Il costo di ogni risposta.** Si calcola dai token che l'API restituisce davvero, con il
  listino in euro, e si salva accanto al messaggio. Un tetto giornaliero
  (`DAILY_BUDGET_EUR`, 5 €) rifiuta con 429 prima di spendere.
- **Il primo strumento.** Il modello può chiedere il saldo di un conto; il codice glielo
  concede solo per i conti dei clienti dell'operatore, e registra i tentativi negati.
- **Lo streaming.** `POST /api/ai/chat/stream` manda la risposta mentre si forma, come
  Server-Sent Events.
- **La categorizzazione con il modello.** Al posto delle parole chiave del Giorno 2, la fa
  Claude attraverso Instructor, che valida la risposta con lo schema Pydantic.

### Dove il codice si discosta dal corso

Il corso è scritto per `gpt-4o-mini`. Con i modelli Claude di oggi tre indicazioni del corso
producono un errore, e il codice le adatta.

- **Niente `temperature`.** Dalla versione dell'API del 21 ottobre 2026 una richiesta che la
  contiene riceve un 400, e l'SDK non ha più il parametro [1]. La leva è `effort`
  (`LLM_EFFORT`, `low` di default), che regola quanto il modello ragiona e quindi quanto
  spende [2].
- **Il ragionamento si paga.** Opus 5.5 ragiona prima di rispondere: quei token si pagano
  come output e rientrano in `max_tokens` [3]. Il costo calcolato li comprende.
- **Instructor con `tool_choice: auto`.** Instructor di norma obbliga il modello a usare lo
  strumento, ma Opus 5.5 rifiuta l'obbligo con un 400 [4]. Il corso lascia l'output
  strutturato sull'SDK di OpenAI; qui resta su Claude, e non serve una chiave OpenAI.

### Le prove

```bash
uv run pytest                              # 60 test, nessuna chiamata a un modello vero
uv run python -m scripts.prove_g4          # le cinque prove della consegna
uv run python -m scripts.misura_stream_interrotto   # la misura dell'estensione
```

Gli script usano l'applicazione vera e gli SDK veri; è finto solo il server del fornitore,
quindi non serve una chiave e non si spende niente. Se il database di test non è sulla
porta 5432, `TEST_DATABASE_URL` dice dove sta. Esito del 16 novembre 2026:

| prova | esito |
|---|---|
| la stessa domanda cambiando solo `DEFAULT_MODEL` | `claude-opus-5-5`: 1.800 token, 0,010748 €; `gpt-4o-mini`: 1.800 token, 0,000378 €. Servizio, endpoint e tipi invariati |
| il conto di Anna Greco, di un altro portafoglio, chiesto in chiaro | lo strumento risponde «conto non disponibile per questo operatore»; nel log `strumento_negato` con operatore e conto; il saldo non compare |
| il tetto di spesa a zero | 429 `RATE_LIMIT` con `Retry-After` in secondi fino a mezzanotte; zero chiamate al modello |
| un movimento incomprensibile, a cui il modello risponde con una categoria inventata | 502 dopo 3 chiamate (1 più 2 tentativi di Instructor, tutte pagate); niente salvato |
| lo stream interrotto a metà | la parte arrivata è salvata, segnata come interrotta, con il costo stimato |

Con una chiave vera nel `.env` la verifica dal vivo è quella del Code Blueprint:

```bash
uv run uvicorn src.main:app --reload
curl -X POST localhost:8000/api/ai/chat -H "Content-Type: application/json" \
  -d '{"session_id":"new","message":"Quanto ha disponibile Paolo Ferri sul conto IT60X0542811101000000123?"}'
# la risposta contiene il saldo vero, e tool_calls la chiamata a get_account_balance
```

### La decisione: dove si conta il costo

- **Scelto**: il provider calcola il costo di ogni chiamata, perché è l'unico che vede il
  consumo restituito dall'API; il servizio somma le chiamate di una domanda e salva il totale
  accanto al messaggio, perché è l'unico che sa a quale conversazione appartiene; il
  `CostTracker` legge quelle somme per il tetto.
- **Scartato**: tutto nel provider, che non sa di chi è la conversazione e non potrebbe mai
  dire quanto costa un operatore; tutto nel servizio, che dovrebbe conoscere il listino e i
  campi di consumo dei due SDK, e il contratto perderebbe senso; un pezzo a parte che li
  avvolge entrambi, che è la strada giusta quando servirà il costo di ogni singola chiamata,
  ma oggi aggiungerebbe un livello senza nessuno che lo usi.
- **Il numero**: una domanda che usa lo strumento fa due chiamate e salva 120 token, non i 60
  dell'ultima (`test_il_giro_dello_strumento_legge_il_saldo_e_conta_due_chiamate`). Il
  limite della scelta è misurato nella prova 4: la categorizzazione fa 3 chiamate pagate e
  ne salva 0. Quando servirà il report per operatore, la decisione si sposta sul pezzo a
  parte, con un registro per chiamata.

### L'estensione: lo stream che sopravvive all'interruzione (la n. 4)

Prima, se l'operatore chiudeva la pagina a metà risposta, nel database non restava niente.
Quella parte di risposta però era già stata generata, e pagata: il tetto non la vedeva.

- **Scelto**: il servizio salva in un blocco `finally`, che gira comunque finisca lo stream,
  e lo protegge dall'annullamento del task (`anyio.CancelScope(shield=True)`), perché quando
  il client chiude Starlette annulla il lavoro in corso [5][6]. La parte arrivata si salva
  segnata come interrotta (colonna `interrupted`), con il costo stimato dai caratteri, circa
  2,7 per token [7]: è una stima per difetto, perché non vede il ragionamento. Lo stream
  verso il fornitore si chiude con `aclosing`, così la generazione si ferma [8].
- **Scartato**: una `StreamingResponse` che chiude da sé il generatore. L'ho scritta e poi
  tolta: togliendola, nessun test falliva, perché con questo stack la chiusura arriva già.
  Scartato anche il controllo di `request.is_disconnected()` a ogni pezzo: una lettura in più
  per pezzo, e non copre il fornitore che cade.
- **Il numero**: con il client che chiude dopo 2 pezzi su 4, prima restavano 0 righe e 0 €;
  ora resta 1 risposta, 33 token stimati, 0,000290 €. I 6 test in
  [`tests/test_pw_g4.py`](tests/test_pw_g4.py) provano i tre modi in cui il server scopre la
  disconnessione, e ogni pezzo della correzione fa fallire almeno un test se lo si toglie.

### La revisione

In [`docs/ai-review/G4.md`](docs/ai-review/G4.md): 13 rilievi sulle quattro voci della
giornata, 6 non corretti con la loro ragione. Due sono stati corretti con una misura: un
indice sulla data dei messaggi, che porta il controllo del tetto da circa 50 a circa 12 ms
su 500.000 messaggi, e la storia della conversazione letta con un `LIMIT`, da 505 a 24 righe
per domanda. Il più importante fra quelli non corretti: con 20 richieste contemporanee il
tetto di 0,05 € lascia spendere 0,214 €.

### Fonti

1. Anthropic, *Migrating to API version 2026-10-21*. https://platform.claude.com/docs/en/api/migration-2026-10-21
2. Anthropic, *Effort*. https://platform.claude.com/docs/en/build-with-claude/effort
3. Anthropic, *Adaptive thinking*. https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking
4. Anthropic, *Define tools* (`tool_choice`). https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools
5. AnyIO, *Cancellation and timeouts*. https://anyio.readthedocs.io/en/stable/cancellation.html
6. ASGI, *HTTP & WebSocket ASGI Message Format*. https://asgi.readthedocs.io/en/latest/specs/www.html
7. Anthropic, *Glossary* (voce «Tokens»). https://platform.claude.com/docs/en/about-claude/glossary
8. Python, *contextlib — aclosing*. https://docs.python.org/3/library/contextlib.html
