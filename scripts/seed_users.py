"""Crea i tre utenti del Giorno 6. Script di sviluppo, da lanciare a mano.

    uv run python -m scripts.seed_users

Si può rilanciare: gli utenti già presenti restano come sono.
"""

import asyncio

from sqlalchemy import select

from src.auth.passwords import hash_password
from src.db.models import AppUser
from src.db.session import AsyncSessionLocal

PASSWORD_DI_SVILUPPO = "bootcamp"

UTENTI = [
    ("mbianchi", "Marco Bianchi", "operator"),
    ("grossi", "Giulia Rossi", "compliance_lead"),
    ("lverdi", "Lucia Verdi", "risk_lead"),
]


async def main() -> None:
    print("!! seed di sviluppo: stessa password per tutti, solo sul proprio ambiente")
    creati = 0
    async with AsyncSessionLocal() as session:
        for username, full_name, role in UTENTI:
            gia_presente = await session.scalar(select(AppUser).where(AppUser.username == username))
            if gia_presente is not None:
                print(f"  {username}: già presente, invariato")
                continue
            session.add(
                AppUser(
                    username=username,
                    full_name=full_name,
                    password_hash=hash_password(PASSWORD_DI_SVILUPPO),
                    role=role,
                )
            )
            creati += 1
        await session.commit()
    print(f"{creati} utenti creati (password: {PASSWORD_DI_SVILUPPO})")


if __name__ == "__main__":
    asyncio.run(main())
