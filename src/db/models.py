# Modelli ORM delle tabelle.
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.session import Base

# Le dimensioni del vettore dipendono dal modello di embedding: bge-m3 ne produce 1024
# (il text-embedding-3-small del corso 1536). Cambiare modello richiede di aggiornare questo
# numero, scrivere una migration e reindicizzare tutti i documenti.
DIMENSIONI_EMBEDDING = 1024


def gen_uuid() -> str:
    return str(uuid.uuid4())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.seq",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_seq", "session_id", "seq"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String, comment="'system' | 'user' | 'assistant' | 'tool'")
    content: Mapped[str] = mapped_column(Text)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_eur: Mapped[Decimal] = mapped_column(Numeric(12, 6), default=Decimal("0"))
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    # Dal Giorno 4: vero se lo streaming si è fermato prima della fine, perché il client ha
    # chiuso o il fornitore è caduto. Il testo allora è parziale e il costo è una stima.
    interrupted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Indicizzata dal Giorno 4: il tetto di spesa somma i costi del giorno a ogni domanda e
    # senza indice PostgreSQL legge tutta la tabella (50 ms su 500.000 messaggi, 12 con).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True
    )
    # L'ordine della conversazione. created_at non basta: su Windows due messaggi salvati di
    # seguito possono ricevere lo stesso istante, e a parità d'istante l'ordine è casuale.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True))

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # il codice cliente
    full_name: Mapped[str] = mapped_column(String(120))
    operator: Mapped[str] = mapped_column(String(64), index=True)  # chi lo ha in portafoglio


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(34), primary_key=True)  # l'IBAN
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    label: Mapped[str] = mapped_column(String(64))  # "principale", "risparmio"
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Movement(Base):
    __tablename__ = "movements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), index=True)
    booking_date: Mapped[date] = mapped_column(Date)  # la data contabile
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # negativo per le uscite


# Dal Giorno 5: i documenti della banca, divisi in passaggi e indicizzati per similarità.


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        # Va dichiarato anche nel modello, altrimenti la prossima --autogenerate lo cancella.
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(String, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(DIMENSIONI_EMBEDDING))
    # SQLAlchemy riserva il nome «metadata» alla classe base.
    chunk_metadata: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
