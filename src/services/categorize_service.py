# src/services/categorize_service.py — lo schema imposto al modello, e validato
import anthropic
import openai
from instructor.core import InstructorRetryException

from src.exceptions import LLMProviderError
from src.llm.factory import Strutturato
from src.observability.cost_tracker import CostTracker
from src.types.categorize import CategorizeRequest, CategorizeResponse


class CategorizeService:
    def __init__(
        self,
        strutturato: Strutturato,
        system_prompt: str,
        costi: CostTracker | None = None,
    ) -> None:
        self.strutturato = strutturato
        self.system_prompt = system_prompt
        self.costi = costi  # il tetto della chat: l'endpoint lo passa sempre

    async def categorize(self, req: CategorizeRequest) -> CategorizeResponse:
        if self.costi is not None:
            await self.costi.verifica()  # prima di spendere: ogni chiamata al modello spende
        s = self.strutturato
        try:
            return await s.client.chat.completions.create(
                model=s.model,
                response_model=CategorizeResponse,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": f"Descrizione: {req.description}\n"
                        f"Importo: {req.amount} {req.currency}",
                    },
                ],
                max_retries=2,  # ogni nuovo tentativo è una chiamata pagata
                max_tokens=1000,  # con Claude comprende il ragionamento, anche a effort low
                **s.opzioni,  # quello che il fornitore vuole o rifiuta: lo sa la factory
            )
        except InstructorRetryException as e:
            # lo schema non rispettato nemmeno dopo i tentativi, già pagati: è un guasto del
            # fornitore, non un bug nostro, e il client riceve il 502 della chat
            raise LLMProviderError(s.fornitore, f"risposta fuori schema: {e}") from e
        except (openai.APIError, anthropic.APIError) as e:  # giù, modello sconosciuto, chiave
            raise LLMProviderError(s.fornitore, str(e)) from e
