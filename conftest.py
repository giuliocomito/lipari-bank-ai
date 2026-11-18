# Prepara l'ambiente dei test prima che qualcosa importi src.
import os
from collections.abc import Iterator

import pytest
from alembic.config import Config

from alembic import command

# Dal Giorno 3 i test usano un database vero, quello di test. DATABASE_URL è sovrascritto
# senza setdefault perché un valore rimasto nell'ambiente porterebbe i test a svuotare il
# database di sviluppo.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://lipari:lipari@localhost:5432/lipari_ai_test"
)
os.environ.setdefault("JWT_SECRET", "segreto-dei-test-lungo-almeno-trentadue-caratteri")


@pytest.fixture(scope="session", autouse=True)
def schema() -> Iterator[None]:
    """Ricrea da zero lo schema di test con le migration, come lo otterrà chi clona il progetto."""
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session", autouse=True)
def modelli_finti() -> Iterator[None]:
    """Sostituisce i modelli con dei finti per tutta la sessione.

    Un modello vero costerebbe e risponderebbe ogni volta in modo diverso. La chat usa un finto
    che ripete la domanda, la categorizzazione la regola a parole chiave, gli embedding sono finti
    ma coerenti. Un test che ha bisogno di un modello preciso installa il suo e poi toglie solo
    quello."""
    from src.api.categorize import get_categorize_service
    from src.llm.factory import get_embedder, get_llm_provider
    from src.main import app
    from tests.finti import CategorizzazioneARegole, ModelloEco, embedder_finto

    app.dependency_overrides[get_llm_provider] = ModelloEco
    app.dependency_overrides[get_categorize_service] = CategorizzazioneARegole
    app.dependency_overrides[get_embedder] = embedder_finto
    yield
    app.dependency_overrides.clear()
