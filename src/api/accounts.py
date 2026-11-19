# Movimenti e spesa di un conto del portafoglio.
import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.deps import UserContext, get_current_user
from src.db.session import get_db
from src.services.account_service import AccountService
from src.types.accounts import MovementIn, MovementOut, MovementPosted, Spending

router = APIRouter(prefix="/api/ai/accounts", tags=["Accounts"])

# L'operatore è l'utente del token; il filtro per portafoglio sta nelle query.
Utente = Annotated[UserContext, Depends(get_current_user)]


@router.get("/{account_id}/movements", response_model=list[MovementOut])
async def movements(
    account_id: str,
    date_from: dt.date,
    date_to: dt.date,
    user: Utente,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[MovementOut]:
    return await AccountService(session).movements_with_owner(
        user.username, account_id, date_from, date_to
    )


@router.post(
    "/{account_id}/movements",
    response_model=MovementPosted,
    status_code=201,
    summary="Registra un movimento e aggiorna il saldo",
    description="Il movimento e il nuovo saldo si scrivono insieme o per niente. "
    "L'importo è al centesimo: con tre decimali la richiesta è rifiutata, non arrotondata.",
)
async def post_movement(
    account_id: str,
    nuovo: MovementIn,
    user: Utente,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MovementPosted:
    return await AccountService(session).post_movement(user.username, account_id, nuovo)


@router.get("/{account_id}/spending", response_model=Spending)
async def spending(
    account_id: str,
    date_from: dt.date,
    date_to: dt.date,
    user: Utente,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Spending:
    return await AccountService(session).spending(user.username, account_id, date_from, date_to)
