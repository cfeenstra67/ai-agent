from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, mapped_column, Mapped


Base = declarative_base()


class SessionModel(Base):
    """
    """
    __tablename__ = "session"

    session_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    started_at: Mapped[datetime]
    ended_at: Mapped[Optional[datetime]]
    ended_by_event_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("event.event_id"))


class EventModel(Base):
    """
    """
    __tablename__ = "event"

    event_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(sa.ForeignKey("session.session_id"))
    command: Mapped[str]
    service: Mapped[str]
    payload: Mapped[str]
    queued_at: Mapped[datetime]
    run_at: Mapped[datetime]
    acknowledged_at: Mapped[Optional[datetime]]
    source_event_id: Mapped[Optional[int]] = mapped_column(sa.ForeignKey("event.event_id"))
