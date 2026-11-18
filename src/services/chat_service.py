# Conversazione con il modello, che può usare lo strumento del saldo.
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime
from decimal import Decimal

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import ChatSession
from src.db.repos import AccountRepository, ChatRepository
from src.exceptions import AccountNotFoundError, ChatSessionNotFoundError, LLMProviderError
from src.llm.client import LLMProvider
from src.llm.stima import stima_interrotta
from src.llm.tools import TOOLS_SCHEMA, costruisci_strumenti
from src.llm.types import LLMResponse, Message
from src.observability.cost_tracker import CostTracker
from src.types.chat import ChatRequest, ChatResponse, ToolCallInfo

FINESTRA = 20  # quanti messaggi di storia entrano nel prompt
GIRI_MASSIMI = 3  # chiamate al modello per domanda; di solito ne bastano due
ARRESO = "Non sono riuscito a completare la richiesta con gli strumenti che ho: riprova più tardi."


def _argomenti(testo: str) -> dict[str, str]:
    """Converte gli argomenti JSON del modello in dizionario; {} se non sono un oggetto."""
    try:
        valori = json.loads(testo)
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in valori.items()} if isinstance(valori, dict) else {}


class ChatService:
    def __init__(
        self,
        session: AsyncSession,
        llm: LLMProvider,
        system_prompt: str,
        tetto_eur: Decimal,
        max_tokens: int = 1000,
    ) -> None:
        self.session = session
        self.repo = ChatRepository(session)
        self.accounts = AccountRepository(session)
        self.costi = CostTracker(self.repo, tetto_eur)
        self.llm = llm
        self.system_prompt = system_prompt
        # limite per singola chiamata; con Claude include anche i token di ragionamento
        self.max_tokens = max_tokens

    async def _conversazione(
        self, req: ChatRequest, user_id: str
    ) -> tuple[ChatSession, list[Message]]:
        """Recupera o crea la conversazione e prepara i messaggi da mandare al modello."""
        storia: list[Message] = []
        if req.session_id != "new":
            chat = await self.repo.find_session(req.session_id, user_id, con_messaggi=False)
            if chat is None:
                raise ChatSessionNotFoundError(req.session_id)
            # la storia va letta prima di salvare il messaggio corrente, altrimenti la domanda
            # arriva al modello due volte. Il LIMIT nel database legge solo gli ultimi FINESTRA
            # messaggi, così una conversazione da 5.000 messaggi non costa 5.000 righe a domanda
            recenti = await self.repo.last_messages(chat.id, FINESTRA)
            storia = [Message(role=m.role, content=m.content) for m in recenti]
        else:
            chat = await self.repo.create_session(user_id=user_id)
        return chat, [
            Message(role="system", content=self.system_prompt),
            *storia,
            Message(role="user", content=req.message),
        ]

    async def _salva(
        self, chat: ChatSession, domanda: str, risposta: LLMResponse, interrotta: bool = False
    ) -> None:
        await self.repo.add_message(chat.id, "user", domanda)
        await self.repo.add_message(
            chat.id,
            "assistant",
            risposta.content,
            tokens=risposta.tokens_used,
            cost_eur=risposta.cost_eur,
            model_used=risposta.model,
            interrupted=interrotta,
        )
        await self.session.commit()  # un solo commit, così domanda e risposta si salvano insieme

    async def _saldo(self, user_id: str, account_id: str) -> Decimal:
        conto = await self.accounts.of_user(user_id, account_id)
        if conto is None:  # lo strumento ha già controllato; questa è una seconda difesa
            raise AccountNotFoundError(account_id)
        return conto.balance

    async def chat(self, req: ChatRequest, user_id: str) -> ChatResponse:
        """Risponde eseguendo gli strumenti richiesti, con il costo sommato su tutti i giri."""
        await self.costi.verifica()  # il tetto si controlla prima di chiamare il modello
        chat, messaggi = await self._conversazione(req, user_id)

        # i conti del portafoglio si leggono una volta per richiesta
        conti = await self.accounts.ids_in_portfolio(user_id)

        async def leggi_saldo(account_id: str) -> Decimal:
            return await self._saldo(user_id, account_id)

        strumenti = costruisci_strumenti(user_id, conti, leggi_saldo)

        risposta = await self.llm.complete(messaggi, self.max_tokens, tools=TOOLS_SCHEMA)
        token, costo = risposta.tokens_used, risposta.cost_eur
        eseguite: list[ToolCallInfo] = []
        giri = 1
        while risposta.tool_calls and giri < GIRI_MASSIMI:
            # il messaggio dell'assistente con le chiamate deve precedere i loro risultati
            messaggi.append(
                Message(role="assistant", content=risposta.content, tool_calls=risposta.tool_calls)
            )
            for richiesta in risposta.tool_calls:  # un risultato per ogni chiamata
                esegui = strumenti.get(richiesta.name)
                esito = (
                    await esegui(richiesta.arguments)
                    if esegui
                    else f"ERRORE: lo strumento {richiesta.name} non esiste."
                )
                messaggi.append(Message(role="tool", content=esito, tool_call_id=richiesta.id))
                eseguite.append(
                    ToolCallInfo(
                        name=richiesta.name, arguments=_argomenti(richiesta.arguments), result=esito
                    )
                )
            risposta = await self.llm.complete(messaggi, self.max_tokens, tools=TOOLS_SCHEMA)
            token, costo = token + risposta.tokens_used, costo + risposta.cost_eur
            giri += 1

        # la risposta salvata riporta token e costo di tutti i giri
        finale = risposta.model_copy(
            update={
                "content": ARRESO if risposta.tool_calls else risposta.content,
                "tokens_used": token,
                "cost_eur": costo,
            }
        )
        await self._salva(chat, req.message, finale)
        return ChatResponse(
            session_id=chat.id,
            reply=finale.content,
            tool_calls=eseguite,
            tokens_used=finale.tokens_used,
            cost_eur=float(finale.cost_eur),  # nella risposta JSON il costo è un numero
            model_used=finale.model,
            created_at=datetime.now(UTC),
        )

    async def chat_stream(self, req: ChatRequest, user_id: str) -> AsyncGenerator[str, None]:
        """Prepara subito la conversazione e restituisce il generatore dei pezzi per il client.

        La preparazione precede l'invio della risposta, così una sessione inesistente o il tetto
        superato producono ancora un 404 o un 429, anziché un errore dentro uno stream già
        partito con 200. Lo streaming non usa strumenti, che restano alla risposta intera.
        """
        await self.costi.verifica()
        chat, messaggi = await self._conversazione(req, user_id)
        return self._pezzi(chat, req.message, messaggi)

    async def _pezzi(
        self, chat: ChatSession, domanda: str, messaggi: list[Message]
    ) -> AsyncGenerator[str, None]:
        """Produce i pezzi della risposta e, in ogni caso, salva la risposta con il suo costo.

        Lo stream può arrivare in fondo, essere interrotto dal client che chiude la pagina (chi
        legge chiude questo generatore con GeneratorExit, oppure Starlette annulla il task con
        CancelledError) o cadere per un errore del fornitore (LLMProviderError). Nel primo caso
        si salva il consumo reale. Negli altri la parte generata è comunque pagata, quindi si
        salva segnata come interrotta, con il costo stimato dai caratteri.
        """
        finale: LLMResponse | None = None
        arrivato: list[str] = []
        try:
            # aclosing propaga la chiusura al generatore del fornitore e alla connessione HTTP,
            # così la generazione si ferma invece di proseguire senza nessuno che la legga
            async with aclosing(self.llm.stream(messaggi, self.max_tokens)) as flusso:
                async for pezzo in flusso:
                    if isinstance(pezzo, LLMResponse):
                        finale = pezzo  # arriva per ultimo, con testo completo, token e costo
                    else:
                        arrivato.append(pezzo)
                        yield pezzo
        finally:
            # scope schermato: se il task è stato annullato, anche gli await qui dentro lo
            # sarebbero e il salvataggio non avverrebbe
            with anyio.CancelScope(shield=True):
                if finale is not None:
                    await self._salva(chat, domanda, finale)
                elif arrivato:
                    stima = stima_interrotta(self.llm.model, messaggi, "".join(arrivato))
                    await self._salva(chat, domanda, stima, interrotta=True)
        if finale is None and not arrivato:
            raise LLMProviderError("stream", "lo stream si è chiuso senza la risposta finale")
