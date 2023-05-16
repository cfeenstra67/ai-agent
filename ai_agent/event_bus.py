import abc
import dataclasses as dc
import json
from datetime import datetime
from typing import Dict, Any, Optional, List

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from ai_agent.models import EventModel, SessionModel


async def create_session(name: str, engine: AsyncEngine) -> SessionModel:
    """
    """
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
        obj = SessionModel(
            name=name,
            started_at=datetime.utcnow()
        )
        session.add(obj)
        await session.commit()

        return obj


@dc.dataclass(frozen=True)
class Event:
    """
    """
    command: str
    payload: Dict[str, Any]


@dc.dataclass(frozen=True)
class QueuedEvent:
    """
    """
    event_id: int
    session_id: int
    command: str
    service: str
    payload: Dict[str, Any]
    source_event_id: Optional[int] = None


class EventBus(abc.ABC):
    """
    """
    @abc.abstractmethod
    async def queue_event(
        self,
        message: Event,
        service: str,
        source_event: Optional[QueuedEvent] = None,
        run_at: Optional[datetime] = None,
    ) -> None:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def ack_event(self, event_id: int, command: str, service: str) -> None:
        """
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    async def get_queued_events(self) -> List[QueuedEvent]:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def end_session(self, source_event_id: Optional[int] = None) -> None:
        """
        """
        raise NotImplementedError


class SQLEventBus(EventBus):
    """
    """
    def __init__(self, engine: AsyncEngine, session_id: int) -> None:
        self.engine = engine
        self.Session = async_sessionmaker(bind=engine)
        self.session_id = session_id
    
    async def _get_session(self, session: AsyncSession) -> SessionModel:
        obj = await session.scalar(
            sa.select(SessionModel)
            .where(SessionModel.session_id == self.session_id)
            .limit(1)
        )
        if obj is None:
            raise SessionNotFound(self.session_id)
        if obj.ended_at:
            raise SessionEnded(self.session_id)
        return obj
    
    async def queue_event(
        self,
        message: Event,
        service: str,
        source_event: Optional[QueuedEvent] = None,
        run_at: Optional[datetime] = None,
    ) -> None:
        queued_at = datetime.utcnow()
        if run_at is None:
            run_at = queued_at

        event = EventModel(
            session_id=self.session_id,
            command=message.command,
            service=service,
            payload=json.dumps(message.payload),
            queued_at=queued_at,
            run_at=run_at,
            source_event_id=source_event and source_event.event_id
        )
        async with self.Session() as session:
            await self._get_session(session)
            session.add(event)
            await session.commit()

    async def ack_event(
        self,
        event_id: int,
        command: str,
        service: str,
    ) -> None:
        now = datetime.utcnow()
        async with self.Session() as session:
            await self._get_session(session)
            event = await session.scalar(
                sa.select(EventModel)
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.event_id == event_id)
                .where(EventModel.command == command)
                .where(EventModel.service == service)
                .where(EventModel.acknowledged_at == None)
                .limit(1)
            )
            if event is not None:
                event.acknowledged_at = now
                session.add(event)
                await session.commit()
    
    async def get_queued_events(self) -> List[QueuedEvent]:
        now = datetime.utcnow()
        async with self.Session() as session:
            await self._get_session(session)
            results = await session.execute(
                sa.select(EventModel)
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.acknowledged_at == None)
                .where(EventModel.run_at <= now)
            )
            out = []
            for event in results.scalars():
                out.append(QueuedEvent(
                    event_id=event.event_id,
                    session_id=event.session_id,
                    command=event.command,
                    service=event.service,
                    payload=json.loads(event.payload),
                    source_event_id=event.source_event_id
                ))
            
            return out
            
    async def end_session(self, source_event_id: Optional[int] = None) -> None:
        async with self.Session() as session:
            obj = await self._get_session(session)
            obj.ended_at = datetime.utcnow()
            obj.ended_by_event_id = source_event_id


class ScopedEventBus:
    """
    """
    def __init__(self, event_bus: EventBus, service: str, source_event: Optional[QueuedEvent] = None) -> None:
        self.event_bus = event_bus
        self.service = service
        self.source_event = source_event

    async def queue_event(self, message: Event, run_at: Optional[datetime] = None) -> None:
        """
        """
        await self.event_bus.queue_event(
            message,
            self.service,
            self.source_event,
            run_at,
        )
    
    async def end_session(self) -> None:
        await self.event_bus.end_session(
            self.source_event and self.source_event.event_id
        )


class SessionEnded(Exception):
    """
    """
    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Session ended: {session_id}")


class SessionNotFound(Exception):
    """
    """
    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")
