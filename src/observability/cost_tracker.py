# Tetto di spesa giornaliero per le chiamate al modello.
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

from src.db.repos import ChatRepository
from src.exceptions import RateLimitError


class CostTracker:
    def __init__(self, repo: ChatRepository, tetto_eur: Decimal) -> None:
        self.repo = repo
        self.tetto_eur = tetto_eur

    async def speso(self, giorno: date | None = None) -> Decimal:
        # Il giorno si calcola qui: un default date.today() nella firma verrebbe valutato una
        # sola volta, all'import, e il processo continuerebbe a contare quel giorno.
        giorno = giorno or datetime.now(UTC).date()
        inizio = datetime.combine(giorno, time.min, tzinfo=UTC)
        return await self.repo.cost_between(inizio, inizio + timedelta(days=1))

    async def verifica(self) -> None:
        """Solleva RateLimitError se il tetto del giorno è raggiunto.

        Va chiamata prima del modello, perché dopo la chiamata la spesa è già avvenuta.
        """
        if await self.speso() >= self.tetto_eur:
            adesso = datetime.now(UTC)
            mezzanotte = datetime.combine(adesso.date() + timedelta(days=1), time.min, tzinfo=UTC)
            raise RateLimitError(int((mezzanotte - adesso).total_seconds()) + 1)
