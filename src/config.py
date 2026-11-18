# Configurazione dell'applicazione e controllo dei valori all'avvio.
import re
import sys
from decimal import Decimal
from typing import Literal

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError


class Settings(BaseSettings):
    """Configurazione letta dalle variabili d'ambiente e dal file `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LipariBank AI"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    # Obbligatorie e non vuote: una riga «DATABASE_URL=» nel .env non basta per avviare.
    # La description compare nel messaggio d'errore quando la variabile manca.
    database_url: str = Field(
        min_length=1,
        description="la stringa di connessione, postgresql+asyncpg://utente:password@host:5432/nome",
    )
    jwt_secret: str = Field(
        min_length=32,  # HS256 richiede una chiave di almeno 256 bit
        description="un segreto di almeno 32 caratteri: "
        'uv run python -c "import secrets; print(secrets.token_urlsafe(48))"',
    )

    # Facoltative all'avvio: servono dal Giorno 4, e la sonda segnala se sono presenti.
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # Dal Giorno 4 il modello è Claude; il prefisso del nome (claude- o gpt-) sceglie il fornitore.
    default_model: str = "claude-opus-5-5"
    # Quanto ragiona Claude prima di rispondere, e quindi quanto spende: low, medium o high.
    llm_effort: Literal["low", "medium", "high"] = "low"
    # Embedding, dal Giorno 5. Anthropic non offre un modello di embedding, quindi si usa
    # bge-m3 in locale, servito da Ollama con un'API compatibile con quella di OpenAI.
    embedding_model: str = "bge-m3"
    embedding_base_url: str = "http://localhost:11434/v1"
    max_tokens_per_request: int = 2000
    daily_budget_eur: Decimal = Decimal("5.00")  # tetto di spesa giornaliero per il modello

    # Dal Giorno 2: le origini a cui il CORS consente di leggere le risposte. Nel .env va in JSON.
    cors_origins: list[str] = ["http://localhost:5173"]


def spiega(errore: ValidationError) -> str:
    """Trasforma l'errore di validazione in un messaggio: quale variabile correggere e come."""
    righe = ["Configurazione non valida: il progetto non parte."]
    for e in errore.errors():
        campo = str(e["loc"][0])
        info = Settings.model_fields.get(campo)
        stato = "manca" if e["type"] == "missing" else f"valore non valido ({e['msg']})"
        cosa = f" Ci va {info.description}." if info and info.description else ""
        righe.append(f"  - {campo.upper()}: {stato}.{cosa}")
    righe.append("Si scrive nel file .env (l'elenco completo sta in .env.example) o nell'ambiente.")
    return "\n".join(righe)


def carica() -> Settings:
    try:
        return Settings()
    except ValidationError as e:
        # sys.exit con una stringa la scrive su stderr ed esce con codice 1, senza traceback.
        sys.exit(spiega(e))
    except SettingsError as e:
        # Dal Giorno 2: un valore illeggibile, per esempio una lista non scritta in JSON.
        trovato = re.search(r'field "(\w+)"', str(e))
        nome = trovato.group(1).upper() if trovato else "una variabile"
        sys.exit(
            "Configurazione non valida: il progetto non parte.\n"
            f"  - {nome}: valore non leggibile. Una lista si scrive in JSON, per esempio "
            '["http://localhost:5173"].'
        )


settings = carica()  # all'import: una configurazione errata ferma il processo prima di servire
