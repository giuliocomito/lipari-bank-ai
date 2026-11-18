from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    """Uno strumento in forma neutra; ogni provider lo traduce nel formato del proprio SDK."""

    name: str
    description: str  # l'unica cosa che il modello legge per decidere se usarlo
    parameters: dict[str, Any]  # lo schema JSON degli argomenti


class ToolCall(BaseModel):
    """Chiamata a uno strumento richiesta dal modello; a eseguirla è l'applicazione."""

    id: str
    name: str
    arguments: str  # JSON generato dal modello, da validare prima dell'uso


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] = Field(default_factory=list)  # se l'assistente chiede strumenti
    tool_call_id: str | None = None  # nei risultati, l'id della chiamata a cui si risponde


class LLMResponse(BaseModel):
    content: str
    tokens_used: int
    cost_eur: Decimal  # Decimal, come la colonna cost_eur dei messaggi
    model: str
    tool_calls: list[ToolCall] = Field(default_factory=list)  # vuota se il modello ha risposto
