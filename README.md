# LipariBank AI

Il backend dell'assistente AI del LipariBank, costruito giornata per giornata nel
bootcamp Python AI. Oggi (Giorno 1) è la fondazione: un'applicazione FastAPI con una
sonda `/health`, una configurazione che si rifiuta di partire se manca qualcosa, e i
controlli di qualità che girano puliti.

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

In [`docs/ai-review/G1.md`](docs/ai-review/G1.md).
