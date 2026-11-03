# src/api/movements.py — l'estratto dei movimenti, caricato in blocco
from typing import Annotated

from fastapi import APIRouter, Depends, Header, UploadFile

from src.services import movement_import
from src.services.import_registry import RegistroImport, get_registro
from src.types.error import ErrorResponse
from src.types.movements import ImportResult

router = APIRouter(prefix="/api/ai", tags=["Movements"])


@router.post(
    "/movements/import",
    response_model=ImportResult,
    summary="Importa un CSV di movimenti",
    description="Importa le righe valide e rende conto, per numero di riga, di ognuna scartata. "
    "Lo stesso file caricato due volte non conta due volte: con la stessa Idempotency-Key, "
    "o senza chiave con lo stesso contenuto, torna l'esito di allora con replayed=true.",
    responses={
        409: {"model": ErrorResponse, "description": "Idempotency-Key già usata per altro file"},
        413: {"model": ErrorResponse, "description": "File oltre i 2 MB"},
        422: {
            "model": ErrorResponse,
            "description": "File vuoto, non CSV, o intestazione sbagliata",
            "content": {
                "application/json": {
                    "example": {
                        "timestamp": "2026-11-03T09:00:00Z",
                        "status": 422,
                        "error": "INVALID_FILE",
                        "message": "L'intestazione deve essere date,description,amount,currency",
                        "path": "/api/ai/movements/import",
                        "details": None,
                    }
                }
            },
        },
    },
)
async def import_movements(
    file: UploadFile,
    registro: Annotated[RegistroImport, Depends(get_registro)],
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            pattern=r"^[A-Za-z0-9-]{8,64}$",
            description="Facoltativa: la chiave che dice «è lo stesso caricamento»",
        ),
    ] = None,
) -> ImportResult:
    # un byte oltre il limite basta a sapere che lo supera: il resto non si legge
    contenuto = await file.read(movement_import.MASSIMO_BYTES + 1)
    return registro.importa(contenuto, idempotency_key)
