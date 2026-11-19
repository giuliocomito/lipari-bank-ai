# Chat con il modello, con la risposta intera o in streaming.
import json
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import UserContext, get_current_user
from src.config import settings
from src.db.session import get_db
from src.exceptions import LLMProviderError
from src.llm.client import LLMProvider
from src.llm.factory import get_llm_provider
from src.llm.prompt import load_prompt
from src.services.chat_service import ChatService
from src.types.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/ai", tags=["Chat"])

SYSTEM_PROMPT = load_prompt("chat_system_v1")


def get_chat_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ChatService:
    return ChatService(
        session, llm, SYSTEM_PROMPT, settings.daily_budget_eur, settings.max_tokens_per_request
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Manda un messaggio all'assistente",
    description='Conversazione a più turni: con session_id "new" se ne apre una nuova.',
)
async def chat(
    req: ChatRequest,
    user: Annotated[UserContext, Depends(get_current_user)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> ChatResponse:
    return await service.chat(req, user_id=user.username)


@router.post("/chat/stream", summary="La stessa chat, con la risposta che arriva mentre si forma")
async def chat_stream(
    req: ChatRequest,
    user: Annotated[UserContext, Depends(get_current_user)],
    service: Annotated[ChatService, Depends(get_chat_service)],
) -> StreamingResponse:
    # un 404 esce qui, prima che lo stream cominci
    pezzi = await service.chat_stream(req, user_id=user.username)

    async def eventi() -> AsyncGenerator[str, None]:
        # Se il client chiude la pagina, la parte già generata la salva il servizio,
        # nel finally di ChatService._pezzi.
        try:
            async for pezzo in pezzi:
                # In JSON, perché un a capo nel testo spezzerebbe l'evento.
                yield f"data: {json.dumps({'text': pezzo}, ensure_ascii=False)}\n\n"
        except LLMProviderError as errore:
            # Il 200 è già stato inviato, quindi l'errore viaggia come evento.
            # La risposta parziale è comunque salvata.
            yield f"event: error\ndata: {json.dumps({'error': errore.code})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(eventi(), media_type="text/event-stream")
