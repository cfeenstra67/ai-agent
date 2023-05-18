import abc
import dataclasses as dc
from datetime import datetime
from typing import Any, Optional, Iterator


@dc.dataclass(frozen=True)
class Event:
    """
    """
    type: str
    payload: Any


@dc.dataclass(frozen=True)
class QueuedEvent:
    """
    """
    event_id: int
    type: str
    payload: Any
    actor_name: str
    source_event_id: Optional[int] = None


class EventBus(abc.ABC):
    """
    """
    @abc.abstractmethod
    def queue_event(self, message: Event) -> None:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    def ack_event(self, event_id: int) -> None:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    def schedule_event(self, message: Event, run_at: datetime) -> None:
        """
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_queued_events(self) -> list[QueuedEvent]:
        """
        """
        raise NotImplementedError


class Commands(abc.ABC):
    """
    """
    @abc.abstractmethod
    def iterate_commands(self, patterns: Optional[list[str]] = None) -> Iterator["Command"]:
        """
        """
        raise NotImplementedError


@dc.dataclass(frozen=True)
class Context:
    """
    """
    event_bus: EventBus
    commands: Commands


@dc.dataclass(frozen=True)
class CommandArgs:
    """
    """
    command: str
    args: list[str]
    body: Optional[str] = None


class CommandParser(abc.ABC):
    """
    """
    @abc.abstractmethod
    def parse(self, message: str) -> list[CommandArgs]:
        """
        """
        raise NotImplementedError


class Command(abc.ABC):
    """
    """
    @abc.abstractmethod
    async def run(self, args: CommandArgs, ctx: Context) -> None:
        """
        """
        raise NotImplementedError


class Service(abc.ABC):
    """
    """
    name: str
    
    @abc.abstractmethod
    def get_commands(self) -> list[Command]:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def handle_event(self, event: QueuedEvent) -> None:
        """
        """
        raise NotImplementedError


class Agent(Service):
    """
    """
    async def handle_message(self, message: str) -> None:
        pass

    async def handle_event(self, event: QueuedEvent) -> None:
        pass


class World:
    """
    """
    commands: Commands

    services: list[Service]








