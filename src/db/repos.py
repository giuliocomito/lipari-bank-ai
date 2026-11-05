# src/db/repos.py — l'unico posto che sa che esiste un database
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.db.models import Account, ChatMessage, ChatSession, Customer, Movement


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, user_id: str) -> ChatSession:
        chat = ChatSession(user_id=user_id)
        self.session.add(chat)
        await self.session.flush()
        return chat

    async def find_session(self, session_id: str, user_id: str) -> ChatSession | None:
        stmt = (
            select(ChatSession)
            .where(ChatSession.id == session_id, ChatSession.user_id == user_id)
            .options(selectinload(ChatSession.messages))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        cost_eur: Decimal = Decimal("0"),
        model_used: str | None = None,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens,
            cost_eur=cost_eur,
            model_used=model_used,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def list_messages(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def messaggi_con_sessione(
        self, user_id: str, giorni: int = 7
    ) -> list[tuple[ChatMessage, datetime]]:
        da = datetime.now(UTC) - timedelta(days=giorni)
        stmt = (
            select(ChatMessage, ChatSession.started_at)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)  # ← la JOIN
            .where(ChatSession.user_id == user_id, ChatMessage.created_at >= da)
            .order_by(ChatMessage.created_at.desc())
        )
        return list((await self.session.execute(stmt)).all())

    async def costo_per_sessione(self, user_id: str) -> list[tuple[str, int, Decimal | None]]:
        stmt = (
            select(
                ChatSession.id,
                func.count(ChatMessage.id).label("messaggi"),
                func.sum(ChatMessage.cost_eur).label("costo"),
            )
            .join(ChatMessage, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .group_by(ChatSession.id)  # ← il GROUP BY
            .order_by(func.sum(ChatMessage.cost_eur).desc())
        )
        return list((await self.session.execute(stmt)).all())


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def of_user(self, username: str, account_id: str) -> Account | None:
        """Il conto, solo se è di un cliente nel portafoglio di questo operatore."""
        return await self.session.scalar(
            select(Account)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Account.id == account_id, Customer.operator == username)
        )

    async def of_customer(self, username: str, customer_id: str) -> list[Account]:
        """I conti di un cliente, solo se il cliente è nel portafoglio di questo operatore."""
        stmt = (
            select(Account)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Customer.id == customer_id, Customer.operator == username)
            .order_by(Account.label)
        )
        return list((await self.session.scalars(stmt)).all())

    async def apply(self, account_id: str, amount: Decimal) -> Decimal | None:
        """Somma l'importo al saldo dentro il database, in un'istruzione sola, e dà il saldo nuovo.

        Nessuna lettura prima: con «leggi il saldo, somma in Python, riscrivi» due richieste
        contemporanee leggerebbero lo stesso saldo, e una delle due somme andrebbe persa.
        Niente commit: la transazione la chiude chi conosce l'operazione intera, il service.
        """
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(balance=Account.balance + amount)
            .returning(Account.balance)
        )
        return await self.session.scalar(stmt)


class MovementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self, account_id: str, booking_date: date, description: str, amount: Decimal
    ) -> Movement:
        """Il movimento, scritto nella transazione aperta: visibile agli altri solo al commit."""
        mov = Movement(
            account_id=account_id, booking_date=booking_date, description=description, amount=amount
        )
        self.session.add(mov)
        await self.session.flush()  # l'id, e i vincoli che scattano qui e non al commit
        return mov

    async def recent(self, username: str, account_id: str, limite: int) -> list[Movement]:
        """Gli ultimi movimenti di un conto del portafoglio, dal più recente."""
        stmt = (
            select(Movement)
            .join(Account, Account.id == Movement.account_id)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Account.id == account_id, Customer.operator == username)
            .order_by(Movement.booking_date.desc())
            .limit(limite)
        )
        return list((await self.session.scalars(stmt)).all())

    async def with_owner(
        self, username: str, account_id: str, dal: date, al: date
    ) -> list[tuple[Movement, str]]:
        """I movimenti di un conto in un periodo, ognuno con il nome dell'intestatario."""
        stmt = (
            select(Movement, Customer.full_name)
            .join(Account, Account.id == Movement.account_id)  # il movimento, al suo conto
            .join(Customer, Customer.id == Account.customer_id)  # il conto, al suo cliente
            .where(
                Account.id == account_id,
                Customer.operator == username,
                Movement.booking_date.between(dal, al),
            )
            .order_by(Movement.booking_date, Movement.id)
        )
        return list((await self.session.execute(stmt)).all())

    async def spent_by_month(
        self, username: str, account_id: str, dal: date, al: date
    ) -> list[tuple[str, Decimal]]:
        """Quanto è uscito dal conto, mese per mese: la somma delle uscite, cambiata di segno."""
        mese = func.to_char(Movement.booking_date, "YYYY-MM")
        stmt = (
            select(mese, func.sum(-Movement.amount))
            .join(Account, Account.id == Movement.account_id)
            .join(Customer, Customer.id == Account.customer_id)
            .where(
                Account.id == account_id,
                Customer.operator == username,
                Movement.booking_date.between(dal, al),
                Movement.amount < 0,  # solo le uscite: gli accrediti non sono spesa
            )
            .group_by(mese)
            .order_by(mese)
        )
        return list((await self.session.execute(stmt)).all())
