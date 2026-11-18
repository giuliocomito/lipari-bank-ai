# LipariBank AI

Il backend dell'assistente AI del LipariBank, costruito giornata per giornata nel
bootcamp Python AI. È un'applicazione FastAPI che classifica e importa i movimenti, li
conserva in PostgreSQL e dal Giorno 4 risponde con Claude di Anthropic, con il costo di
ogni risposta e un tetto di spesa. Il diario completo di ogni giornata sta in
[`docs/giorni/`](docs/giorni/).

## Le giornate

| giorno | cosa aggiunge | etichetta | diario | revisione |
|---|---|---|---|---|
| [1](#giorno-1-il-progetto-e-la-configurazione) | l'applicazione FastAPI con `/health` e una configurazione che non parte se incompleta | `g1` | [g1.md](docs/giorni/g1.md) | [G1.md](docs/ai-review/G1.md) |
| [2](#giorno-2-il-contratto-dellapi) | il contratto dell'API: classificazione di un movimento e importazione di un estratto CSV | `g2` | [g2.md](docs/giorni/g2.md) | [G2.md](docs/ai-review/G2.md) |
| [3](#giorno-3-il-database) | PostgreSQL con clienti, conti, movimenti e una conversazione che sopravvive al riavvio | `g3` | [g3.md](docs/giorni/g3.md) | [G3.md](docs/ai-review/G3.md) |
| [4](#giorno-4-il-modello-linguistico) | un modello linguistico, Claude, con il costo di ogni risposta e un tetto di spesa | `g4` | [g4.md](docs/giorni/g4.md) | [G4.md](docs/ai-review/G4.md) |
| 5 | in corso (RAG su pgvector), branch `giorno-5` | | | |

## Installazione e avvio

Servono uv 0.5 o successivo, che si procura da sé Python 3.12
([installazione](https://docs.astral.sh/uv/getting-started/installation/)), Git e Docker
con Compose (Docker Desktop su Windows e macOS), in funzione: dal Giorno 3 il database
gira in un container.

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
credenziali (`password authentication failed for user "lipari"`): si scrive `"5433:5432"`
in `docker-compose.yml` e `localhost:5433` nel `.env`.

In un altro terminale (in Windows PowerShell 5.1 va scritto `curl.exe`, perché `curl` da
solo è un alias di `Invoke-WebRequest` e risponde in un altro formato):

```bash
curl localhost:8000/health
# {"status":"UP", ..., "environment":"development","credentials":{"openai":false,"anthropic":false}}
```

La documentazione interattiva è su http://localhost:8000/docs.

## La configurazione

Le variabili sono in [`.env.example`](.env.example), ciascuna con un commento. Senza
`DATABASE_URL` e `JWT_SECRET` (almeno 32 caratteri) il progetto non parte: il processo si
ferma con codice 1 e indica la variabile e che cosa ci va. Le chiavi del modello
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) servono solo per interrogare un modello vero;
senza di esse la chat risponde 503, e test e prove non ne hanno bisogno. Dettagli nel
[diario del Giorno 1](docs/giorni/g1.md).

## I controlli

```bash
uv run ruff check .        # lint
uv run ruff format .       # formattazione
uv run mypy src scripts    # tipi, in strict
uv run pytest              # test: dal Giorno 3 parlano con il database lipari_ai_test
```

I test non toccano mai il database di lavoro: `conftest.py` impone `lipari_ai_test`
(modificabile solo con `TEST_DATABASE_URL`) e a ogni esecuzione ricostruisce lo schema da
zero, dalle migration.

## Il repository e le etichette

Ogni giornata ha un'etichetta (*tag*) che conserva il codice com'era alla consegna: `g1`,
`g2`, `g3`, `g4`. `git checkout g2`, per esempio, riporta il progetto alla fine del
Giorno 2; su GitHub l'etichetta si sceglie dal menu dei branch. Dal Giorno 4 ogni giornata
si sviluppa su un branch `giorno-N` e arriva su `main` con una pull request, che ne mostra
in una pagina tutte le modifiche.

I messaggi di commit seguono [Conventional Commits](https://www.conventionalcommits.org/it/v1.0.0/):
un prefisso per il tipo di modifica (`feat` una funzionalità, `fix` una correzione, `docs`
la documentazione, `test` i test, `style` la formattazione) e il giorno fra parentesi,
come in `feat(g3): movimento e saldo insieme`.

Il 16 novembre 2026, prima della pubblicazione, ho riscritto gli otto commit dei primi tre
giorni per adottare la convenzione e sostituire la mia email con l'indirizzo anonimo di
GitHub. I file sono identici, ma i codici dei commit sono cambiati, e le consegne dei
Giorni 1-3 citano quelli vecchi:

| Codice citato nelle consegne | Codice attuale | Commit |
|---|---|---|
| `fb0d28e` | `d5b7226` | feat(g1): setup del progetto |
| `9487394` | `8af6262` | docs(g1): README per un estraneo, .env.example verificato, revisione |
| `51883b8` | `05efc1f` | style(g1): test dell'esempio, riga troppo lunga riformattata da ruff |
| `1ea0b8c` | `8de5429` | docs(g1): README, la prova della ricostruzione cronometrata (tag `g1`) |
| `55f5df6` | `e659d1a` | feat(g2): contratti Pydantic, router, errori in una busta, middleware |
| `6da257d` | `8e53eee` | feat(g2): import rilanciabile, limite di 2 MB, prove, decisione e revisione (tag `g2`) |
| `dd629bb` | `18d9dc9` | feat(g3): PostgreSQL in Docker, modelli SQLAlchemy 2.0, migration Alembic, repository |
| `74352ab` | `630ac54` | feat(g3): movimento e saldo insieme, prove, decisione sul commit e revisione (tag `g3`) |

## Giorno 1: il progetto e la configurazione

L'applicazione FastAPI risponde sulla sonda `/health`, che segnala se le chiavi del
modello ci sono senza mai mostrarle, e la configurazione rifiuta di partire se manca
qualcosa. I controlli di qualità passano senza errori.

```bash
curl localhost:8000/health
```

Per le dipendenze di sviluppo ho scelto il gruppo `[dependency-groups] dev` e ho scartato
l'extra `[project.optional-dependencies]`: il gruppo non compare nei metadati pubblicati e
`uv sync --no-dev` lo esclude dall'immagine di produzione (PEP 735, 2024).

L'estensione è un test che confronta `Settings` con `.env.example` nei due sensi; ho
scartato uno script che generi l'esempio, perché va ricordato. Copre 10 variabili in 0,3
secondi, ed è fallito sia senza `DEFAULT_MODEL` sia con una `REDIS_URL` orfana.

[Diario completo del Giorno 1](docs/giorni/g1.md)

## Giorno 2: il contratto dell'API

L'API classifica un movimento (`POST /api/ai/categorize`) e importa l'estratto CSV che
l'ufficio Operations carica ogni mattina (`POST /api/ai/movements/import`), rendendo conto
di ogni riga. Ogni errore, dal 404 al 500, arriva nella stessa busta e senza traceback.

```bash
curl -X POST localhost:8000/api/ai/movements/import -F "file=@examples/estratto-200.csv"
```

Su 200 righe con 7 sbagliate ho scelto di importare le 193 buone e di restituire le sette
con numero di riga e motivo. Ho scartato il rifiuto del file intero, che per una riga
terrebbe fermi 193 movimenti giusti.

Nell'estensione n. 3 riconosco lo stesso file dall'header `Idempotency-Key` o dallo sha256
del contenuto, e ho scartato il nome del file, che ogni mattina è `estratto.csv`. Caricato
due volte, `examples/estratto-200.csv` lascia il totale a 193.

[Diario completo del Giorno 2](docs/giorni/g2.md)

## Giorno 3: il database

PostgreSQL 16 con pgvector gira in un container, riceve lo schema dalle migration Alembic e
i dati da `scripts/seed_accounts.py`. La conversazione sopravvive al riavvio, e i conti si
leggono solo nel portafoglio dell'operatore: quello di un collega risponde 404
`ACCOUNT_NOT_FOUND`, come un conto inesistente.

```bash
uv run python -m scripts.prova_interruzione
```

Ho affidato il `commit()` al service, al termine dell'operazione, e ho scartato il commit in
`get_db` dopo lo `yield`: con lo scope di default il client riceve 200 per una riga mai
scritta (`test_l_alternativa_scartata_il_commit_dopo_lo_yield`).

Nell'estensione n. 2 movimento e saldo si scrivono in una sola transazione, con un'unica
`UPDATE ... RETURNING balance`; ho scartato il «leggi il saldo, somma in Python, riscrivi».
Con 20 movimenti contemporanei da -1.00 su 100.00 l'`UPDATE` dà 80.00, l'alternativa 99.00.

[Diario completo del Giorno 3](docs/giorni/g3.md)

## Giorno 4: il modello linguistico

Risponde Claude Opus 5.5 di Anthropic, dietro il `Protocol` `LLMProvider` che ammette anche
OpenAI. Il costo di ogni risposta si calcola dai token restituiti dall'API, e un tetto
giornaliero (`DAILY_BUDGET_EUR`, 5 €) rifiuta con 429 prima di spendere. Arrivano anche uno
strumento per il saldo e lo streaming.

```bash
uv run python -m scripts.prove_g4          # le cinque prove della consegna
```

Ho scelto di contare il costo in tre punti: il provider per chiamata, il servizio per
domanda, il `CostTracker` per il tetto; ho scartato il provider o il servizio da soli. Con lo
strumento si salvano 120 token anziché 60; la categorizzazione paga 3 chiamate e ne salva 0.

Nell'estensione n. 4 lo stream interrotto si salva in un `finally` protetto da
`anyio.CancelScope(shield=True)`; ho scartato `request.is_disconnected()` a ogni pezzo. Se il
client chiude dopo 2 pezzi su 4, prima restavano 0 righe, ora 1 risposta da 0,000290 €.

[Diario completo del Giorno 4](docs/giorni/g4.md)
