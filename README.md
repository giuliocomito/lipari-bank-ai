# LipariBank AI

Il backend dell'assistente AI di LipariBank, scritto una giornata alla volta durante il
bootcamp Python AI. È un'applicazione FastAPI che classifica e importa i movimenti bancari,
li conserva in PostgreSQL e risponde alle domande degli operatori con Claude di Anthropic,
tenendo il conto di quanto costa ogni risposta.

## Le giornate

| giorno | argomento | etichetta | diario | revisione |
|---|---|---|---|---|
| 1 | progetto e configurazione | `g1` | [g1.md](docs/giorni/g1.md) | [G1.md](docs/ai-review/G1.md) |
| 2 | contratto dell'API e importazione dei CSV | `g2` | [g2.md](docs/giorni/g2.md) | [G2.md](docs/ai-review/G2.md) |
| 3 | database | `g3` | [g3.md](docs/giorni/g3.md) | [G3.md](docs/ai-review/G3.md) |
| 4 | modello linguistico, costi e streaming | `g4` | [g4.md](docs/giorni/g4.md) | [G4.md](docs/ai-review/G4.md) |
| 5 | ricerca nei documenti con le fonti (RAG), in corso sul branch `giorno-5` | | | |

L'etichetta conserva il codice com'era alla consegna: `git checkout g2` riporta il progetto
alla fine del Giorno 2. Nei diari si trovano le scelte di ogni giornata, le alternative
scartate e le misure che le giustificano.

## Avvio

Servono Git, Docker con Compose e uv 0.5 o successivo, che si procura da sé Python 3.12
([installazione](https://docs.astral.sh/uv/getting-started/installation/)).

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

Poi `curl localhost:8000/health` deve rispondere `"status":"UP"`, e la documentazione
interattiva è su http://localhost:8000/docs. In Windows PowerShell 5.1 si scrive
`curl.exe`, perché `curl` è un alias di `Invoke-WebRequest`. Se la porta 5432 è già occupata
da un altro PostgreSQL, l'errore sembra di credenziali
(`password authentication failed for user "lipari"`): basta scrivere `"5433:5432"` in
`docker-compose.yml` e `localhost:5433` nel `.env`.

## Configurazione

Ogni variabile è spiegata in [`.env.example`](.env.example). Senza `DATABASE_URL` e
`JWT_SECRET` (almeno 32 caratteri) l'applicazione non parte e dice quale variabile manca.
`ANTHROPIC_API_KEY` serve solo per interrogare il modello vero: senza, la chat risponde 503,
mentre test e prove usano modelli finti. Per la ricerca nei documenti serve
[Ollama](https://ollama.com) con il modello degli embedding (`ollama pull bge-m3`).

## Controlli

```bash
uv run ruff check .        # lint
uv run ruff format .       # formattazione
uv run mypy src scripts    # tipi, in strict
uv run pytest              # test: dal Giorno 3 parlano con il database lipari_ai_test
```

I test non toccano mai il database di lavoro: usano `lipari_ai_test`, modificabile solo con
`TEST_DATABASE_URL`, e a ogni esecuzione ne ricostruiscono lo schema dalle migration.

## Branch e commit

Dal Giorno 4 ogni giornata si sviluppa su un branch `giorno-N` e arriva su `main` con una
pull request. I messaggi di commit seguono
[Conventional Commits](https://www.conventionalcommits.org/it/v1.0.0/), con il giorno fra
parentesi, come in `feat(g3): movimento e saldo insieme`. I commit dei primi tre giorni sono
stati riscritti prima della pubblicazione: i codici citati nelle consegne di quei giorni si
ritrovano in [docs/commit-riscritti.md](docs/commit-riscritti.md).
