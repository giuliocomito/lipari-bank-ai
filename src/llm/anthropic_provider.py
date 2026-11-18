import json
import logging
from collections.abc import AsyncGenerator, Sequence
from decimal import Decimal
from typing import Literal

import anthropic
from anthropic import AsyncAnthropic, omit
from anthropic.types import (
    ContentBlock,
    MessageParam,
    TextBlockParam,
    ToolParam,
    ToolResultBlockParam,
    ToolUseBlockParam,
    Usage,
)

from src.exceptions import LLMProviderError
from src.llm.types import LLMResponse, Message, ToolCall, ToolSpec

logger = logging.getLogger(__name__)

# EUR per 1000 token, nell'ordine (input, output). Listino Anthropic in dollari
# (Opus 5.5: 4 $ / 20 $ per milione; Haiku 5.5: 0,10 $ / 0,50 $ fino a 100K token di prompt),
# convertito al cambio BCE del 6/11/2026 (1 EUR = 1,1165 USD). Va aggiornato insieme alla data.
PRICING: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("0.0035826"), Decimal("0.0179131")),
    "claude-haiku-5-5": (Decimal("0.0000896"), Decimal("0.0004478")),
}

Effort = Literal["low", "medium", "high"]
RIFIUTO = "Non posso rispondere a questa richiesta."


def _dividi(messages: list[Message]) -> tuple[str, list[MessageParam]]:
    """Separa il prompt di sistema e traduce il resto nei soli ruoli user e assistant."""
    sistema = "\n\n".join(m.content for m in messages if m.role == "system")
    resto: list[MessageParam] = []
    risultati: list[ToolResultBlockParam] = []
    for m in messages:
        if m.role == "tool":
            risultati.append(
                {"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content}
            )
            continue
        if risultati:  # Anthropic vuole i risultati di un giro in un unico messaggio user
            resto.append({"role": "user", "content": risultati})
            risultati = []
        if m.role == "user":
            resto.append({"role": "user", "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            blocchi: list[TextBlockParam | ToolUseBlockParam] = []
            if m.content:
                blocchi.append({"type": "text", "text": m.content})
            blocchi += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": json.loads(c.arguments)}
                for c in m.tool_calls
            ]
            resto.append({"role": "assistant", "content": blocchi})
        elif m.role == "assistant":
            resto.append({"role": "assistant", "content": m.content})
    if risultati:
        resto.append({"role": "user", "content": risultati})
    return sistema, resto


def _strumenti(tools: list[ToolSpec]) -> list[ToolParam]:
    return [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
    ]


class AnthropicProvider:
    """LLMProvider per i modelli Claude.

    Rispetto a gpt-4o-mini, usato nel corso, cambiano due cose. I modelli Claude attuali
    rispondono 400 a temperature, quindi si regola effort, che decide quanto il modello ragiona
    e di conseguenza quanti token consuma. Il ragionamento è attivo e si paga come output: i
    token di pensiero rientrano in usage.output_tokens e nel limite di max_tokens.
    """

    def __init__(self, client: AsyncAnthropic, model: str, effort: Effort = "low") -> None:
        if model not in PRICING:
            raise ValueError(f"Nessun prezzo per {model}: aggiungilo a PRICING")
        self._client = client
        self._model = model
        self._effort: Effort = effort

    @property
    def model(self) -> str:
        return self._model

    def _risposta(
        self, blocchi: Sequence[ContentBlock], usage: Usage, stop_reason: str | None
    ) -> LLMResponse:
        prezzo_in, prezzo_out = PRICING[self._model]
        # si tiene solo il testo dei blocchi "text"; il ragionamento non si mostra né si salva
        testo = "".join(b.text for b in blocchi if b.type == "text")
        if stop_reason == "refusal":  # bloccata dai classificatori di sicurezza, con stato 200
            logger.warning("modello_rifiuta", extra={"model": self._model})
            testo = RIFIUTO
        return LLMResponse(
            content=testo,
            tokens_used=usage.input_tokens + usage.output_tokens,
            cost_eur=(usage.input_tokens * prezzo_in + usage.output_tokens * prezzo_out) / 1000,
            model=self._model,
            tool_calls=[
                ToolCall(id=b.id, name=b.name, arguments=json.dumps(b.input))
                for b in blocchi
                if b.type == "tool_use"
            ],
        )

    async def complete(
        self, messages: list[Message], max_tokens: int = 500, tools: list[ToolSpec] | None = None
    ) -> LLMResponse:
        sistema, resto = _dividi(messages)
        try:
            r = await self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,  # obbligatorio per Anthropic, che non ha un default
                system=sistema,
                messages=resto,
                tools=_strumenti(tools) if tools else omit,
                output_config={"effort": self._effort},
            )
        except anthropic.APIError as exc:
            raise LLMProviderError("anthropic", str(exc)) from exc
        return self._risposta(r.content, r.usage, r.stop_reason)

    async def stream(
        self, messages: list[Message], max_tokens: int = 500
    ) -> AsyncGenerator[str | LLMResponse, None]:
        sistema, resto = _dividi(messages)
        try:
            async with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=sistema,
                messages=resto,
                output_config={"effort": self._effort},
            ) as s:
                async for testo in s.text_stream:
                    yield testo
                finale = await s.get_final_message()
        except anthropic.APIError as exc:
            raise LLMProviderError("anthropic", str(exc)) from exc
        yield self._risposta(finale.content, finale.usage, finale.stop_reason)
