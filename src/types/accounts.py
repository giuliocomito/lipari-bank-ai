# Contratti dei movimenti di un conto e della spesa mensile.
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class MovementOut(BaseModel):
    booking_date: dt.date
    description: str
    amount: Decimal  # nel JSON è una stringa, "-87.40", così l'importo non passa da un float
    owner: str  # l'intestatario del conto, ricavato con la JOIN


class MonthlySpending(BaseModel):
    month: str  # "2026-07"
    spent: Decimal


class Spending(BaseModel):
    account_id: str
    date_from: dt.date
    date_to: dt.date
    months: list[MonthlySpending]
    total: Decimal


class MovementIn(BaseModel):
    """Movimento da registrare su un conto del portafoglio; un importo negativo è un'uscita."""

    booking_date: dt.date
    description: str = Field(min_length=1, max_length=200)
    # Al massimo due decimali: la colonna è Numeric(12, 2) e il database arrotonderebbe
    # 12.345 a 12.35 senza segnalarlo. Per questo la richiesta si rifiuta già qui.
    amount: Decimal = Field(max_digits=12, decimal_places=2)

    @field_validator("amount")
    @classmethod
    def non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("un movimento da zero non sposta niente")
        return v


class MovementPosted(BaseModel):
    """Movimento registrato e saldo risultante, scritti nella stessa transazione."""

    id: str
    account_id: str
    booking_date: dt.date
    description: str
    amount: Decimal
    balance: Decimal
