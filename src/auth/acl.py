# Quali livelli di visibilità vede ciascun ruolo.
import logging

log = logging.getLogger(__name__)

_PUBLIC: list[str] = ["public"]
_OPERATIVO: list[str] = ["public", "internal"]

# I ruoli non sono una scala: chi lavora sul rischio non vede i documenti della compliance.
_MATRICE: dict[str, list[str]] = {
    "admin": ["public", "internal", "risk_only", "compliance_only"],
    "compliance_lead": ["public", "internal", "compliance_only"],
    "risk_lead": ["public", "internal", "risk_only"],
    "operator": _OPERATIVO,
}


def visible_to(role: str) -> list[str]:
    """I livelli che il ruolo può vedere. Un ruolo sconosciuto vede solo il pubblico e si logga."""
    livelli = _MATRICE.get(role)
    if livelli is None:
        log.warning("ruolo_sconosciuto", extra={"role": role})
        return _PUBLIC
    return livelli
