# src/services/import_registry.py — l'import che si può rilanciare: lo stesso file conta una volta
import hashlib
from collections import OrderedDict
from dataclasses import dataclass

from src.exceptions import ConflictError
from src.services.movement_import import importa_csv
from src.types.movements import ImportResult

# Quante importazioni si ricordano. In memoria finché non arriva il database (Giorno 3):
# senza un tetto, mille caricamenti al minuto sono mille voci al minuto che non escono più
MASSIMO_RICORDATE = 1000


@dataclass(frozen=True)
class Importazione:
    impronta: str  # sha256 del contenuto: dice se la stessa chiave porta lo stesso file
    risultato: ImportResult


class RegistroImport:
    """Le importazioni già fatte, per chiave. Lo stesso file caricato due volte conta una volta."""

    def __init__(self, massimo: int = MASSIMO_RICORDATE) -> None:
        self._viste: OrderedDict[str, Importazione] = OrderedDict()
        self._massimo = massimo
        self.totale_importate = 0  # il conto che non deve raddoppiare

    def importa(self, contenuto: bytes, chiave: str | None = None) -> ImportResult:
        """Importa il file, o restituisce l'esito della volta precedente.

        «Lo stesso file» è la chiave che il chiamante dichiara (Idempotency-Key), come nei
        sistemi di pagamento; se non la dichiara, è il contenuto, byte per byte.
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

        risultato = importa_csv(contenuto)  # un file illeggibile solleva e non si ricorda
        self._viste[chiave] = Importazione(impronta, risultato)
        if len(self._viste) > self._massimo:
            self._viste.popitem(last=False)  # dimentica la più vecchia
        self.totale_importate += risultato.imported_count
        return risultato


_registro = RegistroImport()


def get_registro() -> RegistroImport:
    """La dipendenza dell'endpoint: nei test si sostituisce con dependency_overrides."""
    return _registro
