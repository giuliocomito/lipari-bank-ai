# Corpo comune a tutte le risposte di errore.
from datetime import datetime

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    timestamp: datetime
    status: int
    error: str  # codice stabile per il client, per esempio NOT_FOUND o RATE_LIMIT
    message: str  # il messaggio leggibile da una persona
    path: str
    details: list[str] | None = None
