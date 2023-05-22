import abc
import asyncio
import dataclasses as dc
import itertools
import inspect
from typing import List, Callable, Union, Coroutine

import openai

from ai_agent.agent import Context, Agent, QueuedEvent
from ai_agent.default_agent import AgentMessage


@dc.dataclass(frozen=True)
class AgentMessage:
    """ """

    message: str
    actor: str = "user"
    level: str = "INFO"


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

    @abc.abstractmethod
    async def chat(self, messages: List[AgentMessage]) -> str:
        """
        """
        raise NotImplementedError




class ModularAgent(Agent):
    """
    """
    def __init__(
        self,
        chatter: Chatter,
        message_providers: List[MessageProvider] = ()
    ) -> None:
        self.chatter = chatter
        self.message_providers = message_providers

    def format_command_result(self, event: QueuedEvent, result: str) -> str:
        """ """
        raise NotImplementedError

    def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        """ """
        raise NotImplementedError

    async def chat(self, message: str, ctx: Context) -> str:
        """
        """
        provider_messages = await asyncio.gather(*(
            provider.get_messages(ctx)
            for provider in self.message_providers
        ))
        messages = list(itertools.chain.from_iterable(provider_messages))
        messages.append(AgentMessage(message))

        return await self.chatter.chat(message)
