# Verifica che .env.example abbia una riga per ogni campo della configurazione, e nessuna in più.
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.config import Settings

RADICE = Path(__file__).resolve().parents[1]


def variabili_lette(configurazione: type[BaseSettings]) -> set[str]:
    """Restituisce i nomi delle variabili d'ambiente lette dalla configurazione.

    Tiene conto dell'alias, che sostituisce il nome del campo, e di env_prefix, che lo precede.
    """
    prefisso = configurazione.model_config.get("env_prefix") or ""
    nomi = set()
    for nome, campo in configurazione.model_fields.items():
        alias = campo.validation_alias or campo.alias
        nomi.add((alias if isinstance(alias, str) else f"{prefisso}{nome}").upper())
    return nomi


def variabili_nell_esempio(percorso: Path) -> set[str]:
    righe = percorso.read_text(encoding="utf-8").splitlines()
    return {
        r.split("=", 1)[0].strip() for r in righe if "=" in r and not r.lstrip().startswith("#")
    }


def test_ogni_campo_ha_la_sua_riga_e_nessuna_riga_e_orfana():
    lette = variabili_lette(Settings)
    esempio = variabili_nell_esempio(RADICE / ".env.example")
    assert not lette - esempio, f"campi senza riga in .env.example: {sorted(lette - esempio)}"
    assert not esempio - lette, f"righe che la configurazione non legge: {sorted(esempio - lette)}"


def test_il_confronto_segue_alias_e_prefisso():
    class ConPrefisso(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="LB_")
        database_url: str = ""
        segreto: str = Field(default="", validation_alias="JWT_SECRET")

    assert variabili_lette(ConPrefisso) == {"LB_DATABASE_URL", "JWT_SECRET"}
