# src/lib/chunking.py — il testo in passaggi di ~chunk_size caratteri, con sovrapposizione
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Taglia il testo in passaggi di circa chunk_size caratteri.

    Il taglio cade sulla fine di una frase o di un paragrafo quando ce n'è una nella seconda
    metà della finestra, così un passaggio non si interrompe a metà di un concetto. Due
    passaggi vicini hanno overlap caratteri in comune: una frase che sta a cavallo del taglio
    resta intera in almeno uno dei due.
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
