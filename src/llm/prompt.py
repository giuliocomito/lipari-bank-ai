from pathlib import Path

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    # su Windows la codifica predefinita non è UTF-8 e le lettere accentate darebbero errore
    return (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
