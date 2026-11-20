"""Crea gli utenti del Giorno 6. Script di sviluppo, da lanciare a mano.

    uv run python -m scripts.seed_users

Si può rilanciare: gli utenti già presenti mantengono la password e ricevono la filiale
indicata qui.
"""

import asyncio

from sqlalchemy import select

from src.auth.passwords import hash_password
from src.db.models import AppUser
from src.db.session import AsyncSessionLocal

PASSWORD_DI_SVILUPPO = "bootcamp"

# (username, nome, ruolo, filiale); la filiale vuota è la sede centrale
UTENTI = [
    ("mbianchi", "Marco Bianchi", "operator", "LIP01"),
    ("fneri", "Francesca Neri", "operator", "MIL01"),
    ("grossi", "Giulia Rossi", "compliance_lead", None),
    ("lverdi", "Lucia Verdi", "risk_lead", None),
]


async def main() -> None:
    print("!! seed di sviluppo: stessa password per tutti, solo sul proprio ambiente")
    creati = 0
    async with AsyncSessionLocal() as session:
        for username, full_name, role, branch in UTENTI:
            gia_presente = await session.scalar(select(AppUser).where(AppUser.username == username))
            if gia_presente is not None:
                gia_presente.branch = branch
                print(f"  {username}: già presente, filiale {branch or 'sede centrale'}")
                continue
            session.add(
                AppUser(
                    username=username,
                    full_name=full_name,
                    password_hash=hash_password(PASSWORD_DI_SVILUPPO),
                    role=role,
                    branch=branch,
                )
            )
            creati += 1
        await session.commit()
    print(f"{creati} utenti creati (password: {PASSWORD_DI_SVILUPPO})")


if __name__ == "__main__":
    asyncio.run(main())
