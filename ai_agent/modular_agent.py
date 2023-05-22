import abc
import asyncio
import dataclasses as dc
import itertools
import inspect
from collections import defaultdict
from typing import List, Callable, Union, Coroutine, Dict, Any, Optional

from aiohttp import web

from ai_agent.agent import Context, Agent, QueuedEvent


@dc.dataclass(frozen=True)
class AgentMessage:
    """ """

    message: str
    actor: str = "user"


class MessageProvider(abc.ABC):
    """ """
    @abc.abstractmethod
    async def get_messages(self, ctx: Context) -> List[AgentMessage]:
        """ """
        raise NotImplementedError


@dc.dataclass(frozen=True)
class MessageFactory(MessageProvider):
    get_message: Callable[[Context], Union[str, Coroutine[None, None, str]]]
    actor: str = "user"

    async def get_messages(self, ctx: Context) -> List[AgentMessage]:
        result = self.get_message(ctx)
        if inspect.isawaitable(result):
            result = await result
        return [AgentMessage(result, self.actor)]


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

    async def get_messages(self, ctx: Context) -> List[AgentMessage]:
        scope = self.scope
        if scope is None:
            scope = {}
        elif callable(scope):
            scope = scope()
        
        scope.update({"ctx": ctx})
        result = await self.template.render(scope)
        return [AgentMessage(result)]


class ModularAgent(Agent):
    """
    """
    def __init__(
        self,
        name: str,
        chatter: Chatter,
        result_template: Template = PythonTemplate("{result}"),
        error_template: Template = PythonTemplate("{stack}"),
        message_providers: List[MessageProvider] = (),
    ) -> None:
        from ai_agent.api import get_message_provider

        self.name = name
        self.chatter = chatter
        self.message_providers = [
            get_message_provider(msg_provider)
            for msg_provider in message_providers
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

    async def get_messages(self, message: str, ctx: Context) -> List[AgentMessage]:
        provider_messages = await asyncio.gather(*(
            provider.get_messages(ctx)
            for provider in self.message_providers
        ))
        messages = list(itertools.chain.from_iterable(provider_messages))
        messages.append(AgentMessage(message))
        return messages

    async def chat(self, message: str, ctx: Context) -> str:
        """
        """
        messages = await self.get_messages(message, ctx)

        return await self.chatter.chat(messages)
