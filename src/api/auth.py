# Login: credenziali in ingresso, token in uscita.
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.passwords import hash_password, verify_password
from src.auth.tokens import create_access_token
from src.db.models import AppUser
from src.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["Auth"])

# Hash di una password che nessuno ha: serve a verificare anche quando l'utente non esiste.
DUMMY_HASH = hash_password("nessuno-ha-questa-password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse, summary="Accesso con utente e password")
async def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Verifica le credenziali ed emette un token a scadenza.

    Con credenziali sbagliate risponde 401 senza dire quale delle due era errata.
    """
    utente = await db.scalar(select(AppUser).where(AppUser.username == form.username))
    # L'hash si verifica anche senza utente: con due percorsi di durata diversa, chi prova
    # potrebbe capire dal tempo di risposta quali username esistono.
    atteso = utente.password_hash if utente else DUMMY_HASH
    valida = verify_password(form.password, atteso)

    if utente is None or not valida:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenziali non valide",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(utente.username, utente.role))
