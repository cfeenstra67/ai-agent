from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import mapped_column, Mapped, DeclarativeBase, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class SessionModel(Base):
    """ """

    __tablename__ = "session"

    session_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    started_at: Mapped[datetime]
    ended_at: Mapped[Optional[datetime]]
    ended_by_event_id: Mapped[Optional[int]] = mapped_column(
        sa.ForeignKey("event.event_id")
    )


class EventModel(Base):
    """ """

    __tablename__ = "event"

    event_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(sa.ForeignKey("session.session_id"))
    type: Mapped[str]
    destination: Mapped[str]
    payload: Mapped[str]
    priority: Mapped[int]
    queued_at: Mapped[datetime]
    run_at: Mapped[datetime]
    result: Mapped[Optional[str]]
    error: Mapped[Optional[str]]
    acknowledged_at: Mapped[Optional[datetime]]
    source_event_id: Mapped[Optional[int]] = mapped_column(
        sa.ForeignKey("event.event_id")
    )
    source_event: Mapped[Optional["EventModel"]] = relationship(remote_side=[event_id])
