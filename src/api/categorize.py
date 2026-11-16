# src/api/categorize.py — la categorizzazione, dal modello e validata
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.repos import ChatRepository
from src.db.session import get_db
from src.llm.factory import Strutturato, get_strutturato
from src.llm.prompt import load_prompt
from src.observability.cost_tracker import CostTracker
from src.services.categorize_service import CategorizeService
from src.types.categorize import CategorizeRequest, CategorizeResponse

router = APIRouter(prefix="/api/ai", tags=["Categorize"])

CATEGORIZE_PROMPT = load_prompt("categorize_system_v1")


def get_categorize_service(
    strutturato: Annotated[Strutturato, Depends(get_strutturato)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> CategorizeService:
    # il tetto della chat vale anche qui: ogni chiamata al modello spende, non solo la chat
    costi = CostTracker(ChatRepository(session), settings.daily_budget_eur)
    return CategorizeService(strutturato, CATEGORIZE_PROMPT, costi)


@router.post(
    "/categorize",
    response_model=CategorizeResponse,
    summary="Classifica un movimento",
    description="Dal Giorno 4 con il modello e Instructor: stesso contratto delle regole del G2.",
)
async def categorize(
    req: CategorizeRequest, service: Annotated[CategorizeService, Depends(get_categorize_service)]
) -> CategorizeResponse:
    return await service.categorize(req)
