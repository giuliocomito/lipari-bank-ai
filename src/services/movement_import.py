# Import dei movimenti da CSV: ogni riga viene importata o scartata con il motivo.
import csv

from pydantic import ValidationError

from src.exceptions import FileTooLargeError, InvalidFileError
from src.types.movements import ImportProblem, ImportResult, MovementRow

INTESTAZIONE = ["date", "description", "amount", "currency"]
# La lettura gira dentro un async def e blocca l'event loop. 20.000 righe (750 KB) costano
# ~80 ms, 2 MB circa 0,2 s, che è il blocco più lungo accettabile
MASSIMO_BYTES = 2 * 1024 * 1024


def motivo(errore: ValidationError) -> str:
    """Descrive in una riga il primo campo non valido, per chi ha preparato il file."""
    e = errore.errors()[0]
    campo = ".".join(str(p) for p in e["loc"]) or "riga"
    return f"{campo}: {e['msg']}"


def importa_csv(contenuto: bytes) -> ImportResult:
    if len(contenuto) > MASSIMO_BYTES:
        raise FileTooLargeError(MASSIMO_BYTES)
    if not contenuto.strip():
        raise InvalidFileError("Il file è vuoto")
    try:
        testo = contenuto.decode("utf-8-sig")  # -sig toglie il BOM che Excel aggiunge in testa
    except UnicodeDecodeError:
        raise InvalidFileError("Il file non è testo UTF-8: non è un CSV") from None

    # Ogni riga del file si analizza da sola, così una virgoletta mai chiusa o un campo oltre
    # il limite del modulo csv invalidano solo la propria riga e non le successive
    righe = [r.rstrip("\r") for r in testo.split("\n")]
    if next(csv.reader(righe[:1]), []) != INTESTAZIONE:
        raise InvalidFileError(f"L'intestazione deve essere {','.join(INTESTAZIONE)}")

    importate, problemi = 0, []
    for numero, linea in enumerate(righe[1:], start=2):  # riga del file; la 1 è l'intestazione
        if not linea.strip():
            continue
        try:
            campi = next(csv.reader([linea], strict=True))
        except csv.Error:  # se sfuggisse, sarebbe un 500
            problemi.append(ImportProblem(row=numero, reason="riga illeggibile come CSV"))
            continue
        if len(campi) != len(INTESTAZIONE):
            quanti = "più" if len(campi) > len(INTESTAZIONE) else "meno"
            problemi.append(ImportProblem(row=numero, reason=f"{quanti} di quattro campi"))
            continue
        try:
            MovementRow.model_validate(dict(zip(INTESTAZIONE, campi, strict=True)))
        except ValidationError as e:  # anche questo, se sfuggisse, sarebbe un 500
            problemi.append(ImportProblem(row=numero, reason=motivo(e)))
            continue
        importate += 1
    return ImportResult(imported_count=importate, problems=problemi)
