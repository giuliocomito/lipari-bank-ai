import hashlib
from collections import OrderedDict
from dataclasses import dataclass

from src.exceptions import ConflictError
from src.services.movement_import import importa_csv
from src.types.movements import ImportResult

# Importazioni ricordate, in memoria finché non arriva il database (Giorno 3). Senza un
# limite la memoria crescerebbe di una voce per ogni caricamento, senza mai liberarsi
MASSIMO_RICORDATE = 1000


@dataclass(frozen=True)
class Importazione:
    impronta: str  # sha256 del contenuto, per capire se una chiave già vista porta lo stesso file
    risultato: ImportResult


class RegistroImport:
    """Registro delle importazioni per chiave: un file caricato due volte si importa una volta."""

    def __init__(self, massimo: int = MASSIMO_RICORDATE) -> None:
        self._viste: OrderedDict[str, Importazione] = OrderedDict()
        self._massimo = massimo
        self.totale_importate = 0  # i caricamenti ripetuti non lo incrementano

    def importa(self, contenuto: bytes, chiave: str | None = None) -> ImportResult:
        """Importa il file, o restituisce l'esito dell'importazione precedente.

        Due caricamenti sono lo stesso file se hanno la stessa Idempotency-Key, come nei sistemi
        di pagamento; senza chiave si confronta il contenuto byte per byte.
        """
        impronta = hashlib.sha256(contenuto).hexdigest()
        chiave = chiave or impronta
        precedente = self._viste.get(chiave)
        if precedente is not None:
            if precedente.impronta != impronta:
                raise ConflictError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "Questa Idempotency-Key è già stata usata per un file diverso",
                )
            return precedente.risultato.model_copy(update={"replayed": True})

        risultato = importa_csv(contenuto)  # un file illeggibile solleva e non viene registrato
        self._viste[chiave] = Importazione(impronta, risultato)
        if len(self._viste) > self._massimo:
            self._viste.popitem(last=False)  # dimentica la più vecchia
        self.totale_importate += risultato.imported_count
        return risultato


_registro = RegistroImport()


def get_registro() -> RegistroImport:
    """Dipendenza FastAPI dell'endpoint; nei test si sostituisce con dependency_overrides."""
    return _registro
