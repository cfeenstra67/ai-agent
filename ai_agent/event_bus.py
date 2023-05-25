import dataclasses as dc
import json
from datetime import datetime
from typing import Any, Optional, List

import sqlalchemy as sa
from aiohttp import web
from blinker import signal
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from ai_agent.models import EventModel, SessionModel


DEFAULT_PRIORITY = 0

event_queued = signal("event-queued")


async def create_session(name: str, engine: AsyncEngine) -> SessionModel:
    """ """
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
        obj = SessionModel(name=name, started_at=datetime.utcnow())
        session.add(obj)
        await session.commit()

        return obj


async def get_session(session_id: int, engine: AsyncEngine) -> SessionModel:
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
        session = await session.scalar(
            sa.select(SessionModel)
            .where(SessionModel.session_id == session_id)
        )
        if session is None:
            raise SessionNotFound(session_id)
        return session


@dc.dataclass(frozen=True)
class Event:
    """ """

    type: str
    destination: str
    payload: Any
    priority: int = DEFAULT_PRIORITY


@dc.dataclass(frozen=True)
class QueuedEvent:
    """ """

    event_id: int
    session_id: int
    type: str
    destination: str
    payload: Any
    acknowledged: bool
    priority: int
    result: Optional[str] = None
    source_id: Optional[int] = None
    source_type: Optional[str] = None
    source_destination: Optional[str] = None


async def model_to_queued_event(event: EventModel) -> QueuedEvent:
    source_event = await event.awaitable_attrs.source_event
    return QueuedEvent(
        event_id=event.event_id,
        session_id=event.session_id,
        type=event.type,
        destination=event.destination,
        payload=json.loads(event.payload),
        acknowledged=event.acknowledged_at is not None,
        result=event.result,
        priority=event.priority,
        source_id=source_event and source_event.event_id,
        source_destination=source_event and source_event.destination,
        source_type=source_event and source_event.type,
    )


class EventBus:
    """ """

    def __init__(self, engine: AsyncEngine, session_id: int) -> None:
        self.engine = engine
        self.Session = async_sessionmaker(bind=engine, expire_on_commit=False)
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
        source_event: Optional[QueuedEvent] = None,
        run_at: Optional[datetime] = None,
    ) -> QueuedEvent:
        queued_at = datetime.utcnow()
        if run_at is None:
            run_at = queued_at

        event = EventModel(
            session_id=self.session_id,
            type=message.type,
            destination=message.destination,
            payload=json.dumps(message.payload),
            priority=message.priority,
            queued_at=queued_at,
            run_at=run_at,
            source_event_id=source_event and source_event.event_id,
        )
        async with self.Session() as session:
            await self._get_session(session)
            session.add(event)
            await session.commit()

            queued_event = await model_to_queued_event(event)

            event_queued.send(self, event=queued_event)

            return queued_event

    async def ack_event(
        self,
        event_id: int,
        type: str,
        destination: str,
        result: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow()
        async with self.Session() as session:
            await self._get_session(session)
            event = await session.scalar(
                sa.select(EventModel)
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.event_id == event_id)
                .where(EventModel.type == type)
                .where(EventModel.destination == destination)
                .where(EventModel.acknowledged_at == None)
                .limit(1)
            )
            if event is not None:
                event.acknowledged_at = now
                event.result = result
                event.error = error
                session.add(event)
                await session.commit()

    async def get_queued_events(self) -> List[QueuedEvent]:
        now = datetime.utcnow()
        async with self.Session() as session:
            await self._get_session(session)
            results = await session.execute(
                sa.select(EventModel)
                .options(joinedload(EventModel.source_event))
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.acknowledged_at == None)
                .where(EventModel.run_at <= now)
                .order_by(EventModel.queued_at)
            )
            out = []
            for event in results.scalars():
                out.append(await model_to_queued_event(event))

            return out

    async def get_event_history(
        self,
        type: str,
        destination: str,
        limit: int,
    ) -> List[QueuedEvent]:
        async with self.Session() as session:
            await self._get_session(session)
            results = await session.execute(
                sa.select(EventModel)
                .options(joinedload(EventModel.source_event))
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.acknowledged_at != None)
                .where(EventModel.type == type)
                .where(EventModel.destination == destination)
                .order_by(EventModel.acknowledged_at)
                .limit(limit)
            )
            out = []
            for event in results.scalars():
                out.append(await model_to_queued_event(event))
            
            return out

    async def get_event(self, event_id: int) -> Optional[QueuedEvent]:
        async with self.Session() as session:
            await self._get_session(session)
            event = await session.scalar(
                sa.select(EventModel)
                .options(joinedload(EventModel.source_event))
                .where(EventModel.session_id == self.session_id)
                .where(EventModel.event_id == event_id)
                .limit(1)
            )
            if event is None:
                return None
            return await model_to_queued_event(event)

    async def end_session(self, source_event_id: Optional[int] = None) -> None:
        async with self.Session() as session:
            obj = await self._get_session(session)
            obj.ended_at = datetime.utcnow()
            obj.ended_by_event_id = source_event_id


def event_bus_aiohttp_app(event_bus: EventBus) -> web.Application:
    app = web.Application()

    # TODO: add real implementation
    async def event_bus_post(request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app.add_routes([web.post("/", event_bus_post)])

    return app


class SessionEnded(Exception):
    """ """

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Session ended: {session_id}")


class SessionNotFound(Exception):
    """ """

    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        super().__init__(f"Session not found: {session_id}")
