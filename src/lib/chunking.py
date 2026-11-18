def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Divide il testo in passaggi di circa chunk_size caratteri.

    Se nella seconda metà della finestra finisce una frase o un paragrafo, il taglio cade
    lì, così un passaggio non si interrompe a metà di un concetto. Due passaggi vicini
    condividono overlap caratteri: una frase più corta della sovrapposizione, se il taglio
    la spezza, si ritrova intera nel passaggio successivo.
    """
    if not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end < len(text):
            for sep in [". ", ".\n", "? ", "! ", "\n\n"]:
                idx = text.rfind(sep, start, end)
                if idx > start + chunk_size // 2:
                    end = idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
        if end >= len(text):
            break
    return chunks
