# Movimenti e spesa per periodo dei conti in portafoglio.
import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repos import AccountRepository, MovementRepository
from src.exceptions import AccountNotFoundError, InvalidPeriodError
from src.types.accounts import (
    MonthlySpending,
    MovementIn,
    MovementOut,
    MovementPosted,
    Spending,
)


class AccountService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.accounts = AccountRepository(session)
        self.movements = MovementRepository(session)

    async def post_movement(
        self, username: str, account_id: str, nuovo: MovementIn
    ) -> MovementPosted:
        """Registra il movimento e aggiorna il saldo nella stessa transazione."""
        if await self.accounts.of_user(username, account_id) is None:
            raise AccountNotFoundError(account_id)
        mov = await self.movements.add(
            account_id, nuovo.booking_date, nuovo.description, nuovo.amount
        )
        saldo = await self.accounts.apply(account_id, nuovo.amount)
        if saldo is None:  # il conto è sparito fra la verifica e l'aggiornamento
            raise AccountNotFoundError(account_id)
        # Un solo commit per le due scritture: se l'aggiornamento del saldo fallisce, il movimento
        # non resta registrato. Se fallisce il commit, l'eccezione parte prima della risposta e il
        # client riceve un errore invece di un 201 per un movimento inesistente.
        await self.session.commit()
        return MovementPosted(
            id=mov.id,
            account_id=account_id,
            booking_date=mov.booking_date,
            description=mov.description,
            amount=mov.amount,
            balance=saldo,
        )

    async def _verifica(self, username: str, account_id: str, dal: dt.date, al: dt.date) -> None:
        if dal > al:
            raise InvalidPeriodError()
        if await self.accounts.of_user(username, account_id) is None:
            raise AccountNotFoundError(account_id)

    async def movements_with_owner(
        self, username: str, account_id: str, dal: dt.date, al: dt.date
    ) -> list[MovementOut]:
        await self._verifica(username, account_id, dal, al)
        righe = await self.movements.with_owner(username, account_id, dal, al)
        return [
            MovementOut(
                booking_date=m.booking_date,
                description=m.description,
                amount=m.amount,
                owner=intestatario,
            )
            for m, intestatario in righe
        ]

    async def spending(self, username: str, account_id: str, dal: dt.date, al: dt.date) -> Spending:
        await self._verifica(username, account_id, dal, al)
        mesi = await self.movements.spent_by_month(username, account_id, dal, al)
        return Spending(
            account_id=account_id,
            date_from=dal,
            date_to=al,
            months=[MonthlySpending(month=m, spent=s) for m, s in mesi],
            total=sum((s for _, s in mesi), Decimal("0")),  # con Decimal la somma resta esatta
        )
