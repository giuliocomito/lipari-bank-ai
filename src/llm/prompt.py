# src/llm/prompt.py — i prompt sono file versionati in src/llm/prompts/
from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    # utf-8 esplicito: su Windows, senza, una lettera accentata nel prompt diventa un errore
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
