# src/types/accounts.py — i movimenti di un conto, e la spesa per mese
import datetime as dt
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator


class MovementOut(BaseModel):
    booking_date: dt.date
    description: str
    amount: Decimal  # nel JSON esce come stringa, "-87.40": un importo non passa da un float
    owner: str  # l'intestatario del conto, dalla JOIN


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
    """Un movimento da registrare su un conto del portafoglio. Negativo = uscita."""

    booking_date: dt.date
    description: str = Field(min_length=1, max_length=200)
    # Al centesimo, e non uno di più: la colonna è Numeric(12, 2), e un 12.345 il database lo
    # arrotonderebbe a 12.35 senza dirlo. Un importo che cambia per strada si rifiuta qui.
    amount: Decimal = Field(max_digits=12, decimal_places=2)

    @field_validator("amount")
    @classmethod
    def non_zero(cls, v: Decimal) -> Decimal:
        if v == 0:
            raise ValueError("un movimento da zero non sposta niente")
        return v


class MovementPosted(BaseModel):
    """Il movimento registrato e il saldo dopo di lui, scritti nella stessa transazione."""

    id: str
    account_id: str
    booking_date: dt.date
    description: str
    amount: Decimal
    balance: Decimal
