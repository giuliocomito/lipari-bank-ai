# tests/test_pw_g4.py — l'estensione del Giorno 4: lo stream interrotto lascia il testo e il costo
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from decimal import Decimal

import anyio
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from starlette.requests import ClientDisconnect

from src.db.models import ChatMessage
from src.db.session import AsyncSessionLocal, engine
from src.exceptions import LLMProviderError
from src.llm.factory import get_llm_provider
from src.llm.stima import stima_interrotta
from src.llm.types import LLMResponse, Message, ToolSpec
from src.main import app
from src.services.chat_service import ChatService
from src.types.chat import ChatRequest

CLAUDE = "claude-opus-5-5"
PEZZI = ["Il saldo ", "del conto principale ", "di Paolo Ferri ", "è di 48.200,00 euro."]
SISTEMA = "Sei l'assistente."
DOMANDA = "Quanto ha Paolo sul conto principale?"


class ModelloAPezzi:
    """Un modello finto che risponde a pezzi, con una pausa fra l'uno e l'altro.

    Con cade_dopo=N, dopo N pezzi solleva l'errore del fornitore, come una rete che cade.
    """

    model = CLAUDE

    def __init__(self, cade_dopo: int | None = None) -> None:
        self.cade_dopo = cade_dopo
        self.connessione_chiusa = False  # quella con il fornitore: un modello vero la chiude

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        raise NotImplementedError

    async def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        try:
            for i, pezzo in enumerate(PEZZI):
                if i == self.cade_dopo:
                    raise LLMProviderError("finto", "connessione caduta a metà")
                await anyio.sleep(0.02)
                yield pezzo
            yield LLMResponse(
                content="".join(PEZZI), tokens_used=300, cost_eur=Decimal("0.004"), model=CLAUDE
            )
        finally:
            self.connessione_chiusa = True  # nel provider vero: l'uscita da messages.stream()


@pytest.fixture(autouse=True)
async def tabelle_vuote() -> AsyncIterator[None]:
    await engine.dispose()
    async with engine.begin() as c:
        await c.execute(text("TRUNCATE chat_messages, chat_sessions CASCADE"))
    yield


@pytest.fixture(autouse=True)
def override_ripristinati() -> Iterator[None]:
    prima = dict(app.dependency_overrides)
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(prima)


async def risposte_salvate() -> list[ChatMessage]:
    async with AsyncSessionLocal() as s:
        return list(
            (await s.scalars(select(ChatMessage).where(ChatMessage.role == "assistant"))).all()
        )


def costo_atteso(testo: str) -> Decimal:
    messaggi = [Message(role="system", content=SISTEMA), Message(role="user", content=DOMANDA)]
    return stima_interrotta(CLAUDE, messaggi, testo).cost_eur


# ---------------------------------------------------------------- la proprietà
async def test_lo_stream_interrotto_lascia_il_testo_arrivato_e_il_suo_costo():
    """Il client legge due pezzi su quattro e chiude: la risposta resta, segnata e pagata."""
    modello = ModelloAPezzi()
    async with AsyncSessionLocal() as s:
        servizio = ChatService(s, modello, SISTEMA, Decimal("5"))
        pezzi = await servizio.chat_stream(
            ChatRequest(session_id="new", message=DOMANDA), user_id="mbianchi"
        )
        letti = [await anext(pezzi), await anext(pezzi)]
        await pezzi.aclose()  # il client chiude la pagina
        # e la chiusura arriva fino al fornitore: la generazione si ferma, non continua a vuoto
        assert modello.connessione_chiusa
    [risposta] = await risposte_salvate()
    assert risposta.content == "".join(letti) == "Il saldo del conto principale "
    assert risposta.interrupted is True
    # prima dell'estensione: nessuna riga, 0 € registrati. Ora il costo stimato del parziale
    assert risposta.cost_eur == costo_atteso(risposta.content).quantize(Decimal("0.000001"))
    assert risposta.cost_eur > 0


async def test_una_risposta_completa_non_e_interrotta_e_porta_il_costo_vero():
    async with AsyncSessionLocal() as s:
        servizio = ChatService(s, ModelloAPezzi(), SISTEMA, Decimal("5"))
        pezzi = await servizio.chat_stream(
            ChatRequest(session_id="new", message=DOMANDA), user_id="mbianchi"
        )
        assert [p async for p in pezzi] == PEZZI
    [risposta] = await risposte_salvate()
    assert risposta.interrupted is False and risposta.cost_eur == Decimal("0.004")


# ---------------------------------------------------------------- la trappola: nessuno avvisa
@pytest.mark.parametrize(
    "modo",
    ["asgi23-aspetta-il-modello", "asgi23-browser-lento", "asgi24-invio-fallisce"],
)
async def test_la_disconnessione_vera_del_client_arriva_fino_al_database(
    modo: str, monkeypatch: pytest.MonkeyPatch
):
    """Il client chiude la pagina dopo il primo pezzo, e il server lo scopre a modo suo.

    Il nostro codice non riceve nessuna chiamata «il client è andato». Con ASGI 2.3, quello
    che dichiara uvicorn, il server manda http.disconnect e Starlette annulla il task:
    l'annullamento arriva mentre il servizio aspetta il modello, o mentre un pezzo sta ancora
    partendo verso un browser lento a riceverlo. Con ASGI 2.4 Starlette non ascolta: è l'invio
    del pezzo successivo a fallire con un errore di rete, e il generatore resta fermo su un
    yield. In tutti e tre i casi la risposta va salvata, e dentro la richiesta.
    """
    app.dependency_overrides[get_llm_provider] = ModelloAPezzi
    spec = "2.4" if modo.startswith("asgi24") else "2.3"
    corpo = json.dumps({"session_id": "new", "message": DOMANDA}).encode()
    primo_pezzo_inviato = anyio.Event()
    inviati: list[dict[str, object]] = []
    richiesta_letta = False

    async def receive() -> dict[str, object]:
        nonlocal richiesta_letta
        if not richiesta_letta:
            richiesta_letta = True
            return {"type": "http.request", "body": corpo, "more_body": False}
        await primo_pezzo_inviato.wait()
        if spec == "2.4":
            await anyio.sleep_forever()  # con 2.4 il server non avvisa: se ne accorge l'invio
        return {"type": "http.disconnect"}

    async def send(messaggio: dict[str, object]) -> None:
        if messaggio["type"] == "http.response.body" and messaggio.get("body"):
            if spec == "2.4" and primo_pezzo_inviato.is_set():
                raise OSError("connessione chiusa dal client")
            primo_pezzo_inviato.set()
            if modo == "asgi23-browser-lento":  # l'invio aspetta, e lì arriva l'annullamento
                await anyio.sleep(0.5)
        inviati.append(messaggio)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": spec},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/ai/chat/stream",
        "raw_path": b"/api/ai/chat/stream",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json"), (b"host", b"test")],
        "client": ("127.0.0.1", 50000),
        "server": ("test", 80),
    }
    ordine: list[str] = []
    salva = ChatService._salva

    async def salva_e_annota(self: ChatService, *args: object, **kwargs: object) -> None:
        await salva(self, *args, **kwargs)  # type: ignore[arg-type]
        ordine.append("risposta salvata")

    monkeypatch.setattr(ChatService, "_salva", salva_e_annota)
    # con 2.4 l'errore di rete esce dall'applicazione, ed è il server a gestirlo: qui conta
    # solo che cosa è rimasto nel database
    with anyio.fail_after(5), contextlib.suppress(ClientDisconnect, OSError):
        await app(scope, receive, send)  # type: ignore[arg-type]
    ordine.append("richiesta finita")  # subito, senza await in mezzo

    corpi = [m for m in inviati if m["type"] == "http.response.body" and m.get("body")]
    assert 1 <= len(corpi) < len(PEZZI)  # il client ha ricevuto solo l'inizio
    # il salvataggio avviene dentro la richiesta, con la sua sessione del database ancora
    # aperta; non più tardi, quando il garbage collector raccoglie un generatore abbandonato
    assert ordine == ["risposta salvata", "richiesta finita"]
    [risposta] = await risposte_salvate()
    assert risposta.interrupted is True and risposta.content.startswith("Il saldo ")
    assert risposta.cost_eur > 0


async def test_il_fornitore_che_cade_a_meta_lascia_il_parziale_e_un_evento_di_errore():
    app.dependency_overrides[get_llm_provider] = lambda: ModelloAPezzi(cade_dopo=2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/api/ai/chat/stream", json={"session_id": "new", "message": DOMANDA})
    eventi = [e for e in r.text.split("\n\n") if e]
    assert r.status_code == 200  # già partito: l'errore non può più essere uno stato HTTP
    assert eventi[-2] == 'event: error\ndata: {"error": "LLM_PROVIDER_ERROR"}'
    assert eventi[-1] == "data: [DONE]"
    [risposta] = await risposte_salvate()
    assert risposta.interrupted is True
    assert risposta.content == "Il saldo del conto principale "
