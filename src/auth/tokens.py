# Emissione e verifica dei token di accesso.
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import HTTPException, status

from src.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(minutes=30)


def create_access_token(subject: str, role: str) -> str:
    """Emette un token firmato per l'utente, valido trenta minuti."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Verifica firma e scadenza e restituisce il payload; altrimenti solleva un 401.

    L'algoritmo ammesso lo decide il server: un token con «alg: none» viene respinto.
    """
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token scaduto",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token non valido",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
