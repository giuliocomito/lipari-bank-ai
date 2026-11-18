# Categorizzazione tramite modello, con output vincolato allo schema e validato.
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
        self.costi = costi  # lo stesso tetto di spesa della chat; l'endpoint lo passa sempre

    async def categorize(self, req: CategorizeRequest) -> CategorizeResponse:
        if self.costi is not None:
            await self.costi.verifica()  # il tetto si controlla prima di chiamare il modello
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
                max_tokens=1000,  # con Claude include il ragionamento, anche con effort low
                **s.opzioni,  # parametri specifici del fornitore, decisi dalla factory
            )
        except InstructorRetryException as e:
            # lo schema non è rispettato nemmeno dopo i tentativi (già pagati). Lo trattiamo come
            # guasto del fornitore, e il client riceve lo stesso 502 della chat
            raise LLMProviderError(s.fornitore, f"risposta fuori schema: {e}") from e
        except (openai.APIError, anthropic.APIError) as e:  # servizio giù, modello o chiave errati
            raise LLMProviderError(s.fornitore, str(e)) from e
