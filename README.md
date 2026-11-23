# LipariBank AI

Questo repository contiene il backend dell'assistente AI di LipariBank, sviluppato una giornata
alla volta durante il bootcamp Python AI. Si tratta di un'applicazione FastAPI che classifica e
importa i movimenti bancari, li conserva in un database PostgreSQL e risponde alle domande degli
operatori servendosi del modello Claude di Anthropic; per ciascuna risposta l'applicazione
registra anche il costo sostenuto.

## Le giornate

| Giorno | Argomento | Etichetta | Diario | Revisione |
|---|---|---|---|---|
| 1 | impostazione del progetto e configurazione | `g1` | [g1.md](docs/giorni/g1.md) | [G1.md](docs/ai-review/G1.md) |
| 2 | contratto dell'API e importazione dei file CSV | `g2` | [g2.md](docs/giorni/g2.md) | [G2.md](docs/ai-review/G2.md) |
| 3 | persistenza nel database | `g3` | [g3.md](docs/giorni/g3.md) | [G3.md](docs/ai-review/G3.md) |
| 4 | modello linguistico, costi e streaming | `g4` | [g4.md](docs/giorni/g4.md) | [G4.md](docs/ai-review/G4.md) |
| 5 | ricerca nei documenti con indicazione delle fonti (RAG) e taratura della soglia | `g5` | [g5.md](docs/giorni/g5.md) | [G5.md](docs/ai-review/G5.md) |
| 6 | autenticazione con JWT, documenti filtrati per ruolo e per filiale, riscrittura della domanda | | [g6.md](docs/giorni/g6.md) | [G6.md](docs/ai-review/G6.md) |

Ogni etichetta conserva il codice nello stato in cui si trovava al momento della consegna: il
comando `git checkout g2`, per esempio, riporta il progetto alla fine del Giorno 2. I diari
documentano le scelte compiute in ciascuna giornata, le alternative scartate e le misure che
giustificano le decisioni.

## Estensione del Giorno 5: la soglia di somiglianza

Questa estensione non rientra fra le quattro proposte dal corso. Quando la somiglianza fra la
domanda e i passaggi recuperati resta sotto una certa soglia, il sistema dichiara di non
saper rispondere e non interpella il modello. La soglia indicata dal corso, pari a 0,35,
lascia però arrivare al modello tutte le domande a cui i documenti non danno risposta. Ho quindi
fissato la soglia sulla base dei dati e ne ho misurato l'effetto su un gruppo di domande tenute da parte,
contando quante domande prive di risposta vengono fermate e quante domande provviste di risposta
vanno perse.

```bash
uv run python -m scripts.misura_soglia   # ogni soglia fra 0,35 e 0,65, sui due gruppi di domande
uv run python -m scripts.prove_g5        # le quattro prove della consegna
```

Ho scelto la soglia di 0,50, che è la più alta fra quelle che non escludono alcuna domanda
provvista di risposta. Ho scartato la soglia di 0,55 perché, pur fermando qualche domanda priva
di risposta in più, esclude tre domande provviste di risposta. Sulle 12 domande del gruppo di
verifica, il passaggio da 0,35 a 0,50 porta le domande prive di risposta fermate da 0 su 6 a
3 su 6, mentre quelle provviste di risposta restano 6 su 6. I dettagli si trovano nel
[diario del Giorno 5](docs/giorni/g5.md).

## Estensione del Giorno 6: i permessi per filiale

I documenti interni sono filtrati anche in base alla filiale. Un documento associato a una o più
filiali è visibile a chi lavora in una di esse e a chi lavora nella sede centrale, mentre un
documento privo di filiali vale per tutta la banca.

```bash
uv run python -m scripts.misura_filiale  # 20.000 passaggi sintetici, prima e dopo il filtro
uv run python -m scripts.prove_g6        # le prove della consegna, con i token veri
```

Ho scelto di leggere la filiale dell'utente dal database, all'interno della stessa query di
ricerca, e ho scartato l'alternativa di inserirla nel token, poiché il contenuto del token è
leggibile in chiaro e non si aggiorna prima della scadenza. Il filtro richiede 0,3 ms in più.
Il suo costo reale riguarda la completezza dei risultati, perché nel caso peggiore, senza la
ricerca iterativa, 21 domande su 50 restavano senza alcun risultato e il richiamo scendeva al
58%. Il richiamo indica
quanti dei passaggi corretti, individuati con una ricerca esatta, vengono restituiti dalla
ricerca approssimata. Con la ricerca iterativa di pgvector, che continua a
scorrere l'indice finché i passaggi che superano il filtro sono sufficienti, le domande senza
risultati scendono a 0 su 50 e il richiamo sale al 94%. I dettagli si trovano nel
[diario del Giorno 6](docs/giorni/g6.md).

## Installazione e avvio

Per installare il progetto servono Git, Docker con Compose e uv in versione 0.5 o successiva;
uv provvede da sé a procurare Python 3.12
([istruzioni di installazione](https://docs.astral.sh/uv/getting-started/installation/)).

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

Al termine dell'installazione, il comando `curl localhost:8000/health` deve restituire
`"status":"UP"`, e la documentazione interattiva dell'API è disponibile all'indirizzo
http://localhost:8000/docs. In Windows PowerShell 5.1 occorre scrivere `curl.exe`, perché
`curl` è un alias di `Invoke-WebRequest`. Se la porta 5432 è già occupata da un'altra istanza di
PostgreSQL, l'errore che si ottiene sembra dovuto alle credenziali
(`password authentication failed for user "lipari"`); in tal caso è sufficiente scrivere
`"5433:5432"` in `docker-compose.yml` e `localhost:5433` nel file `.env`.

## Configurazione

Ogni variabile è descritta nel file [`.env.example`](.env.example). Se manca `DATABASE_URL` o
`JWT_SECRET`, che deve contenere almeno 32 caratteri, l'applicazione non si avvia e indica quale
variabile è assente. La variabile `ANTHROPIC_API_KEY` serve soltanto per interrogare il modello
reale: in sua assenza la chat risponde con il codice 503, mentre i test e le prove usano modelli
simulati. A partire dal Giorno 5 la ricerca nei documenti richiede [Ollama](https://ollama.com)
con il modello che calcola gli embedding (`ollama pull bge-m3`), cioè le rappresentazioni
vettoriali dei testi con cui si misura la loro somiglianza.

## Controlli

```bash
uv run ruff check .        # lint
uv run ruff format .       # formattazione
uv run mypy src scripts    # tipi, in strict
uv run pytest              # test: dal Giorno 3 parlano con il database lipari_ai_test
```

I test non accedono mai al database di lavoro. Usano infatti `lipari_ai_test`, che può essere
sostituito soltanto indicando un altro indirizzo nella variabile `TEST_DATABASE_URL`, e a ogni
esecuzione ne ricostruiscono lo schema a partire dalle migration.

## Branch e commit

Dal Giorno 4 ogni giornata viene sviluppata su un branch `giorno-N` e confluisce in `main`
attraverso una pull request. I messaggi di commit seguono la convenzione
[Conventional Commits](https://www.conventionalcommits.org/it/v1.0.0/) e riportano il giorno fra
parentesi, come in `feat(g3): movimento e saldo insieme`. I commit dei primi tre giorni sono
stati riscritti prima della pubblicazione del repository; la corrispondenza fra i codici citati
nelle consegne di quei giorni e i codici attuali si trova in
[docs/commit-riscritti.md](docs/commit-riscritti.md).
