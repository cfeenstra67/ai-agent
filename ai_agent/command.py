import abc
import dataclasses as dc
from typing import Optional, Iterator, Tuple, List

from sqlalchemy.ext.asyncio import AsyncEngine

from ai_agent.event_bus import QueuedEvent, ScopedEventBus


@dc.dataclass(frozen=True)
class Context:
    """
    """
    event_bus: ScopedEventBus
    commands: "Commands"
    engine: AsyncEngine


class Command(abc.ABC):
    """
    """
    name: str

    @abc.abstractmethod
    def get_description(self) -> str:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def run(self, event: QueuedEvent, ctx: Context) -> None:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def handle_error(self, error: Exception, event: QueuedEvent, ctx: Context) -> None:
        """
        """
        raise NotImplementedError


class Commands(abc.ABC):
    """
    """
    def __init__(self, services: List["Service"]) -> None:
        self.commands = {}
        self.command_services = {}

        for service in services:
            for command in service.get_commands():
                # TODO: validate not duplicates
                self.commands[command.name] = command
                self.command_services[command.name] = service

    def get_command(self, name: str) -> Tuple[Command, "Service"]:
        return self.commands[name], self.command_services[name]

    def get_commands(self, patterns: Optional[list[str]] = None) -> Iterator[Command]:
        # TODO: filter commands w/ patterns
        return iter(self.commands.values())


class MessageProvider(abc.ABC):
    """
    """
    @abc.abstractmethod
    async def get_messages(self, service: str, ctx: Context) -> None:
        """
        """
        raise NotImplementedError


from ai_agent.service import Service
