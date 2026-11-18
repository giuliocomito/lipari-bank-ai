# Repository delle chat, dei conti e dei movimenti.
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

    async def find_session(
        self, session_id: str, user_id: str, con_messaggi: bool = True
    ) -> ChatSession | None:
        """Restituisce la conversazione solo se è di user_id, con i messaggi se richiesti."""
        stmt = select(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
        if con_messaggi:
            stmt = stmt.options(selectinload(ChatSession.messages))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def last_messages(self, session_id: str, limite: int) -> list[ChatMessage]:
        """Restituisce in ordine gli ultimi messaggi, leggendone dal database solo `limite`."""
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq.desc())
            .limit(limite)
        )
        recenti = list((await self.session.scalars(stmt)).all())
        return recenti[::-1]  # dal più vecchio al più recente, nell'ordine atteso dal modello

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tokens: int = 0,
        cost_eur: Decimal = Decimal("0"),
        model_used: str | None = None,
        interrupted: bool = False,
    ) -> ChatMessage:
        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            tokens=tokens,
            cost_eur=cost_eur,
            model_used=model_used,
            interrupted=interrupted,
        )
        self.session.add(msg)
        await self.session.flush()
        return msg

    async def list_messages(self, session_id: str) -> list[ChatMessage]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.seq)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def messaggi_con_sessione(
        self, user_id: str, giorni: int = 7
    ) -> list[tuple[ChatMessage, datetime]]:
        da = datetime.now(UTC) - timedelta(days=giorni)
        stmt = (
            select(ChatMessage, ChatSession.started_at)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.user_id == user_id, ChatMessage.created_at >= da)
            .order_by(ChatMessage.seq.desc())
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
            .group_by(ChatSession.id)
            .order_by(func.sum(ChatMessage.cost_eur).desc())
        )
        return list((await self.session.execute(stmt)).all())

    async def cost_between(self, inizio: datetime, fine: datetime) -> Decimal:
        """Somma il costo dei messaggi creati in [inizio, fine); zero se non ce ne sono."""
        speso = await self.session.scalar(
            select(func.coalesce(func.sum(ChatMessage.cost_eur), 0)).where(
                ChatMessage.created_at >= inizio, ChatMessage.created_at < fine
            )
        )
        return Decimal(speso or 0)


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def of_user(self, username: str, account_id: str) -> Account | None:
        """Restituisce il conto solo se il suo cliente è nel portafoglio dell'operatore."""
        return await self.session.scalar(
            select(Account)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Account.id == account_id, Customer.operator == username)
        )

    async def of_customer(self, username: str, customer_id: str) -> list[Account]:
        """Restituisce i conti del cliente solo se è nel portafoglio dell'operatore."""
        stmt = (
            select(Account)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Customer.id == customer_id, Customer.operator == username)
            .order_by(Account.label)
        )
        return list((await self.session.scalars(stmt)).all())

    async def ids_in_portfolio(self, username: str) -> set[str]:
        """Restituisce gli IBAN dei conti dei clienti nel portafoglio dell'operatore."""
        stmt = (
            select(Account.id)
            .join(Customer, Customer.id == Account.customer_id)
            .where(Customer.operator == username)
        )
        return set((await self.session.scalars(stmt)).all())

    async def apply(self, account_id: str, amount: Decimal) -> Decimal | None:
        """Somma l'importo al saldo con un solo UPDATE e restituisce il saldo aggiornato.

        Il saldo non si legge prima: leggendolo, sommando in Python e riscrivendolo, due
        richieste contemporanee partirebbero dallo stesso valore e una somma andrebbe persa.
        Il commit spetta al service, che conosce l'operazione intera.
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
        """Scrive il movimento nella transazione aperta; gli altri lo vedono solo dopo il commit."""
        mov = Movement(
            account_id=account_id, booking_date=booking_date, description=description, amount=amount
        )
        self.session.add(mov)
        await self.session.flush()  # assegna l'id e fa scattare subito i vincoli
        return mov

    async def recent(self, username: str, account_id: str, limite: int) -> list[Movement]:
        """Restituisce gli ultimi movimenti di un conto del portafoglio, dal più recente."""
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
        """Restituisce i movimenti del conto nel periodo, ognuno con il nome dell'intestatario."""
        stmt = (
            select(Movement, Customer.full_name)
            .join(Account, Account.id == Movement.account_id)
            .join(Customer, Customer.id == Account.customer_id)
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
        """Somma le uscite del conto mese per mese, con il segno invertito."""
        mese = func.to_char(Movement.booking_date, "YYYY-MM")
        stmt = (
            select(mese, func.sum(-Movement.amount))
            .join(Account, Account.id == Movement.account_id)
            .join(Customer, Customer.id == Account.customer_id)
            .where(
                Account.id == account_id,
                Customer.operator == username,
                Movement.booking_date.between(dal, al),
                Movement.amount < 0,  # gli accrediti non contano come spesa
            )
            .group_by(mese)
            .order_by(mese)
        )
        return list((await self.session.execute(stmt)).all())
