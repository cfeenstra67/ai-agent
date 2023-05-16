import abc
import dataclasses as dc
from typing import Optional, List, Tuple, Iterator

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from ai_agent.command import Command
from ai_agent.event_bus import ScopedEventBus, QueuedEvent


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
    async def run(self, event: QueuedEvent, ctx: "Context") -> None:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def handle_error(self, error: Exception, event: QueuedEvent, ctx: Context) -> None:
        """
        """
        raise NotImplementedError


class MessageProvider(abc.ABC):
    """
    """
    name: str

    @abc.abstractmethod
    async def get_messages(self, service: str, ctx: "Context") -> None:
        """
        """
        raise NotImplementedError


class Commands:
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

    def get_commands(self, patterns: Optional[List[str]] = None) -> Iterator[Command]:
        # TODO: filter commands w/ patterns
        return iter(self.commands.values())


class MessageProviders:
    """
    """
    def __init__(self, services: List["Service"]) -> None:
        self.message_providers = {}

        for service in services:
            for message_provider in service.get_message_providers():
                self.message_providers[message_provider.name] = message_provider
        

    def get_message_providers(self, patterns: Optional[List[str]] = None) -> Iterator[MessageProvider]:
        # TODO: filter message providers w/ patterns
        return iter(self.message_providers.values())


@dc.dataclass(frozen=True)
class Context:
    """
    """
    event_bus: ScopedEventBus
    commands: Commands
    message_providers: MessageProviders
    engine: AsyncEngine


class Service(abc.ABC):
    """
    """
    name: str

    def get_sqlalchemy_metadata(self) -> Optional[sa.MetaData]:
        return None
    
    @abc.abstractmethod
    def get_commands(self) -> List[Command]:
        """
        """
        raise NotImplementedError
    
    @abc.abstractmethod
    def get_message_providers(self) -> List[MessageProvider]:
        """
        """
        raise NotImplementedError
