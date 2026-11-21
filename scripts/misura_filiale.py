"""Misura che cosa costa il filtro per filiale su una ricerca approssimata (estensione G6).

Prepara nel database di test un corpus sintetico: 20.000 passaggi da 1024 dimensioni, 2.000
documenti, 20 filiali. I vettori sono raggruppati intorno a 200 argomenti, come quelli veri, e
ogni domanda è il vettore di un passaggio esistente con un po' di rumore. Poi confronta, per
l'operatore mbianchi della filiale LIP01, tre versioni della ricerca dei primi 5 passaggi:

- solo ruolo: la query del Giorno 6 prima dell'estensione;
- ruolo e filiale: la query attuale, con la join sulle filiali;
- ruolo e filiale con hnsw.iterative_scan (pgvector 0.8), che continua a scorrere l'indice
  finché i passaggi che superano il filtro bastano.

Per ciascuna riporta il piano usato davvero e il tempo di esecuzione nel database, letti da
EXPLAIN ANALYZE (mediana e 95° percentile su 50 domande); il richiamo, cioè quanti dei 5
passaggi giusti, trovati con una ricerca esatta sugli stessi filtri, la ricerca approssimata
restituisce; e quante domande restano a vuoto, senza nessun passaggio, pur avendone di visibili.
Il database di test viene svuotato all'inizio.

    uv run python -m scripts.misura_filiale
"""

import asyncio
import json
import os
import random
import statistics
import time

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-delle-prove-lungo-almeno-trentadue-caratteri")

from sqlalchemy import TextClause, text  # noqa: E402

from scripts import seed_users  # noqa: E402
from src.auth.acl import visible_to  # noqa: E402
from src.db.models import DIMENSIONI_EMBEDDING  # noqa: E402
from src.db.session import engine  # noqa: E402
from src.services.retrieval_service import RetrievalService  # noqa: E402

PASSAGGI = 20_000
DOMANDE = 50
K = 5

SOLO_RUOLO = text(
    """
    SELECT c.id FROM document_chunks AS c
    WHERE c.visibility = ANY(:livelli)
    ORDER BY c.embedding <=> CAST(:q AS vector)
    LIMIT :k
    """
)
# la query attuale, senza la soglia di somiglianza: con vettori casuali escluderebbe tutto
_SOGLIA = "WHERE 1 - (c.embedding <=> CAST(:q AS vector)) >= :soglia\n          AND"
_COLONNE = (
    "SELECT c.id, c.document_id, c.content,\n"
    "               1 - (c.embedding <=> CAST(:q AS vector)) AS similarity"
)
RUOLO_E_FILIALE = text(
    RetrievalService.SQL_PER_RUOLO.text.replace(_SOGLIA, "WHERE").replace(_COLONNE, "SELECT c.id")
)


def esatta(query: TextClause) -> TextClause:
    """La stessa ricerca senza indice: le distanze si calcolano tutte, poi si ordina.

    Un'impostazione come enable_indexscan non basta: asyncpg riusa il piano già preparato per
    lo stesso testo SQL, e la ricerca «esatta» userebbe di nuovo l'indice approssimato.
    """
    interna, _ = query.text.split("ORDER BY")
    interna = interna.replace(
        "SELECT c.id", "SELECT c.id, c.embedding <=> CAST(:q AS vector) AS d", 1
    )
    return text(
        f"WITH candidati AS MATERIALIZED ({interna}) SELECT id FROM candidati ORDER BY d LIMIT :k"
    )


SCENARI = {
    # ogni argomento ha documenti di livelli e filiali diversi: il caso tipico
    "argomenti misti": ("(d / 200 + d) % 20", "(d / 200 * 7 + d / 20) % 20", "(d / 200 + d) % 10"),
    # tutti i documenti di un argomento hanno lo stesso livello e la stessa filiale: il caso
    # peggiore, come una procedura che riguarda una sola filiale
    "argomenti di una sola filiale": ("d % 20", "(d / 20) % 20", "d % 10"),
}


def corpus(livello: str, filiale: str, assegnato: str) -> list[str]:
    """Le istruzioni che preparano il corpus; d è il numero del documento."""
    d_passaggio, d_documento = "(g / 10)", "substr(document_id, 4)::int"
    return [
        "TRUNCATE document_chunks, document_branches",
        "DROP INDEX IF EXISTS ix_document_chunks_embedding",
        "DROP TABLE IF EXISTS centri_misura",
        f"""
        CREATE TABLE centri_misura AS
        SELECT i, ARRAY(SELECT random() - 0.5 FROM generate_series(1, {DIMENSIONI_EMBEDDING})
                        WHERE i >= 0) AS v
        FROM generate_series(0, 199) AS i
        """,
        f"""
        INSERT INTO document_chunks
            (id, document_id, chunk_index, content, embedding, chunk_metadata, visibility)
        SELECT md5(g::text), 'doc' || (g / 10), g % 10, 'passaggio sintetico',
               ARRAY(SELECT c.v[j] + (random() - 0.5) * 0.6
                     FROM generate_series(1, {DIMENSIONI_EMBEDDING}) AS j)::vector,
               '{{}}'::json,
               CASE WHEN {livello.replace("d", d_passaggio)} < 8 THEN 'public'
                    WHEN {livello.replace("d", d_passaggio)} < 18 THEN 'internal'
                    WHEN {livello.replace("d", d_passaggio)} = 18 THEN 'risk_only'
                    ELSE 'compliance_only' END
        FROM generate_series(0, {PASSAGGI - 1}) AS g
        JOIN centri_misura AS c ON c.i = ((g / 10) * 37) % 200
        """,
        "DROP TABLE centri_misura",
        # sette documenti interni su dieci appartengono a una filiale, gli altri a tutta la banca
        f"""
        INSERT INTO document_branches (document_id, branch)
        SELECT DISTINCT document_id,
               CASE {filiale.replace("d", d_documento)}
                    WHEN 0 THEN 'LIP01' WHEN 1 THEN 'MIL01'
                    ELSE 'F' || lpad(({filiale.replace("d", d_documento)})::text, 2, '0') END
        FROM document_chunks
        WHERE visibility = 'internal' AND {assegnato.replace("d", d_documento)} < 7
        """,
        "SET maintenance_work_mem = '512MB'",
        """CREATE INDEX ix_document_chunks_embedding ON document_chunks
           USING hnsw (embedding vector_cosine_ops)""",
        "ANALYZE document_chunks",
        "ANALYZE document_branches",
    ]


async def esegui(
    query: TextClause, parametri: dict[str, object], impostazioni: list[str]
) -> tuple[list[str], float, bool]:
    """Gli id trovati, il tempo di esecuzione nel database e se il piano usa l'indice HNSW."""
    async with engine.connect() as conn, conn.begin():
        for impostazione in impostazioni:
            await conn.execute(text(impostazione))
        righe = (await conn.execute(query, parametri)).scalars().all()
        spiegazione = text("EXPLAIN (ANALYZE, FORMAT JSON) " + str(query))
        piano = (await conn.execute(spiegazione, parametri)).scalar_one()
    if isinstance(piano, str):
        piano = json.loads(piano)
    usa_indice = "ix_document_chunks_embedding" in json.dumps(piano)
    return [str(r) for r in righe], float(piano[0]["Execution Time"]), usa_indice


async def misura(scenario: str, istruzioni: list[str]) -> None:
    inizio = time.perf_counter()
    async with engine.begin() as conn:
        for istruzione in istruzioni:
            await conn.execute(text(istruzione))
    print()
    print(f"== {scenario}: {PASSAGGI} passaggi pronti in {time.perf_counter() - inizio:.0f} s")

    rnd = random.Random(6)
    async with engine.connect() as conn:
        vicini = await conn.execute(
            text("SELECT embedding::text FROM document_chunks ORDER BY md5(id || 'g6') LIMIT :n"),
            {"n": DOMANDE},
        )
        basi = [json.loads(v) for v in vicini.scalars().all()]
    domande = [str([x + rnd.uniform(-0.1, 0.1) for x in base]) for base in basi]
    livelli = visible_to("operator")
    iterativa = ["SET LOCAL hnsw.iterative_scan = relaxed_order"]
    varianti: list[tuple[str, TextClause, list[str]]] = [
        ("solo ruolo (prima)", SOLO_RUOLO, []),
        ("ruolo e filiale (dopo)", RUOLO_E_FILIALE, []),
        ("ruolo e filiale, iterative_scan", RUOLO_E_FILIALE, iterativa),
    ]
    print(f"{'ricerca':<32} {'HNSW':>6} {'mediana':>8} {'95°':>8} {'richiamo':>8} {'a vuoto':>8}")
    for nome, query, impostazioni in varianti:
        tempi, richiami, conteggi, con_indice = [], [], [], 0
        for i, q in enumerate(domande):
            parametri = {"q": q, "k": K, "livelli": livelli, "utente": "mbianchi"}
            if i == 0:  # riscalda la cache, non si conta
                await esegui(query, parametri, impostazioni)
            trovati, ms, indice = await esegui(query, parametri, impostazioni)
            giusti, _, _ = await esegui(esatta(query), parametri, [])
            tempi.append(ms)
            conteggi.append(len(trovati))
            con_indice += indice
            if giusti:  # una domanda senza passaggi visibili non entra nel richiamo
                richiami.append(len(set(trovati) & set(giusti)) / len(giusti))
        print(
            f"{nome:<32} {con_indice:>3}/{len(domande)}"
            f" {statistics.median(tempi):>6.1f}ms"
            f" {statistics.quantiles(tempi, n=20)[18]:>6.1f}ms"
            f" {statistics.mean(richiami):>8.0%}"
            f" {conteggi.count(0):>5}/{len(domande)}"
        )


async def main() -> None:
    await seed_users.main()
    for scenario, (livello, filiale, assegnato) in SCENARI.items():
        await misura(scenario, corpus(livello, filiale, assegnato))
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
