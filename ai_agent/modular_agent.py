import abc
import asyncio
import dataclasses as dc
import fnmatch
import itertools
from collections import defaultdict
from typing import List, Callable, Union, Dict, Any, Optional

from aiohttp import web

from ai_agent.agent import Context, Agent, QueuedEvent, AgentMessage, Command
from ai_agent.utils.asyncio import maybe_await


class MessageProvider(abc.ABC):
    """ """
    @abc.abstractmethod
    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        """ """
        raise NotImplementedError


class Chatter(abc.ABC):
    """
    """
    def aiohttp_app(self) -> Optional[web.Application]:
        """
        """
        return None

    @abc.abstractmethod
    async def chat(self, messages: List[AgentMessage]) -> str:
        """
        """
        raise NotImplementedError


class Template(abc.ABC):
    """
    """
    @abc.abstractmethod
    async def render(self, scope: Dict[str, Any]) -> str:
        """
        """
        raise NotImplementedError


@dc.dataclass(frozen=True)
class PythonTemplate(Template):
    """
    """
    template_string: str
    default_value: Optional[str] = "<unknown>"

    async def render(self, scope: Dict[str, Any]) -> str:
        input_dict = scope
        if self.default_value is not None:
            input_dict = defaultdict(
                lambda: self.default_value,
                scope
            )
        return self.template_string.format_map(input_dict)


@dc.dataclass(frozen=True)
class MessageTemplate(MessageProvider):
    """
    """
    template: Template
    scope: Optional[Union[Callable[[], Dict[str, Any]], Dict[str, Any]]] = None

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        scope = self.scope
        if scope is None:
            scope = {}
        elif callable(scope):
            scope = scope()
        
        scope.update({"ctx": ctx, "agent": agent})
        result = await self.template.render(scope)
        return [AgentMessage(result)]


class CommandFilter(abc.ABC):
    """
    """
    @abc.abstractmethod
    def filter_commands(self, commands: List[Command]) -> List[Command]:
        """
        """
        raise NotImplementedError


@dc.dataclass(frozen=True)
class GlobCommandFilter(CommandFilter):
    """
    """
    patterns: List[str]

    def filter_commands(self, commands: List[Command]) -> List[Command]:
        out = []
        for command in commands:
            if not any(
                fnmatch.fnmatch(command.name, pattern)
                for pattern in self.patterns
            ):
                continue
            out.append(command)
        return out


class ModularAgent(Agent):
    """
    """
    def __init__(
        self,
        name: str,
        chatter: Chatter,
        *,
        result_template: Optional[Template] = None,
        error_template: Optional[Template] = None,
        message_providers: List[MessageProvider] = (),
        command_filters: List[CommandFilter] = (),
    ) -> None:
        from ai_agent.api import get_message_provider, get_command_filter
        from ai_agent.default_formatters import DefaultResultTemplate, DefaultErrorTemplate

        if result_template is None:
            result_template = DefaultResultTemplate()
        
        if error_template is None:
            error_template = DefaultErrorTemplate()

        self.name = name
        self.chatter = chatter
        self.message_providers = [
            get_message_provider(msg_provider)
            for msg_provider in message_providers
        ]
        self.command_filters = [
            get_command_filter(cmd_filter)
            for cmd_filter in command_filters
        ]
        self.result_template = result_template
        self.error_template = error_template

    def aiohttp_app(self) -> Optional[web.Application]:
        return self.chatter.aiohttp_app()

    async def format_command_result(self, event: QueuedEvent, result: str) -> str:
        """ """
        return await self.result_template.render({"event": event, "result": result})

    async def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        """ """
        return await self.error_template.render({"event": event, "error": error, "stack": stack})

    def filter_commands(self, commands: List[Command]) -> List[Command]:
        for filter in self.command_filters:
            commands = filter.filter_commands(commands)
        return commands

    async def get_messages(self, message: str, ctx: Context) -> List[AgentMessage]:
        provider_messages = await asyncio.gather(*(
            provider.get_messages(self.name, ctx)
            for provider in self.message_providers
        ))
        messages = list(itertools.chain.from_iterable(provider_messages))
        messages.append(AgentMessage(message))
        return messages

    async def chat(self, messages: List[AgentMessage], ctx: Context) -> str:
        """
        """
        return await self.chatter.chat(messages)
