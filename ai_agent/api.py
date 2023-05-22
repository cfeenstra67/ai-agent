import dataclasses as dc
import inspect
import textwrap
from typing import Optional, Callable, Any, List, Coroutine, Union, Awaitable

from aiohttp import web

from ai_agent.agent import Command, CommandRequest, Context, CommandDocumentation, Agent
from ai_agent.event_bus import QueuedEvent
from ai_agent.modular_agent import AgentMessage, MessageProvider


@dc.dataclass(frozen=True)
class FunctionCommand(Command):
    """
    """
    name: str
    usage: str
    func: Callable[[CommandRequest, Context], Any]
    description: str
    validate_func: Optional[Callable[[List[str], Optional[str]], Optional[int]]] = None

    def get_docs(self) -> CommandDocumentation:
        return CommandDocumentation(
            usage=self.usage,
            description=self.description
        )

    def validate(self, args, body):
        if self.validate_func:
            return self.validate_func(args, body)
        return None
    
    async def __call__(self, cmd, ctx):
        result = self.func(cmd, ctx)
        if inspect.isawaitable(result):
            result = await result
        return result


def command(
    func: Optional[Callable[[CommandRequest, Context], Any]] = None,
    *,
    name: Optional[str] = None,
    usage: Optional[str] = None,
    description: Optional[str] = None,
    validate: Optional[Callable[[List[str], Optional[str]], Optional[int]]] = None,
):
    def dec(f):
        f_name = name or f.__name__
        f_usage = usage or f_name
        f_description = description
        if f_description is None and getattr(f, "__doc__", None):
            f_description = textwrap.dedent(f.__doc__).strip()
        elif f_description is None:
            f_description = f_usage

        f._cmd = FunctionCommand(
            name=f_name,
            usage=f_usage,
            description=f_description,
            func=f,
            validate_func=validate
        )
        return f

    if func is None:
        return dec

    return dec(func)


def get_command(obj: Any) -> Command:
    if isinstance(obj, Command):
        return obj
    if callable(obj) and isinstance(getattr(obj, "_cmd", None), Command):
        return obj._cmd
    raise TypeError(f"Invalid command: {obj}")


@dc.dataclass(frozen=True)
class FunctionMessageProvider(MessageProvider):
    """
    """
    name: str
    func: Callable[[Context], Union[List[AgentMessage], Coroutine[None, None, List[AgentMessage]]]]

    async def get_messages(self, ctx: Context) -> List[AgentMessage]:
        result = self.func(ctx)
        if inspect.isawaitable(result):
            result = await result
        return result


def message_provider(
    func: Optional[Callable[[Context], Coroutine[None, None, List[AgentMessage]]]] = None,
    *,
    name: Optional[str] = None,
):
    def dec(f):
        nonlocal name

        f_name = name
        if f_name is None:
            f_name = f.__name__

        f._msg_provider = FunctionMessageProvider(f_name, f)
        return f

    if func is None:
        return dec
    
    return dec(func)


def get_message_provider(obj: Any) -> MessageProvider:
    if isinstance(obj, MessageProvider):
        return obj
    if callable(obj) and isinstance(getattr(obj, "_msg_provider", None), MessageProvider):
        return obj._msg_provider
    raise TypeError(f"Invalid message provider: {obj}")


@dc.dataclass(frozen=True)
class AgentWrapper(Agent):
    """
    """
    agent: Agent
    name: dc.InitVar[Optional[str]] = None
    aiohttp_app: dc.InitVar[
        Optional[Callable[..., web.Application | None]]
    ] = None
    format_command_result: dc.InitVar[
        Optional[Callable[[QueuedEvent, str], Awaitable[str]]]
    ] = None
    format_command_error: dc.InitVar[
        Optional[Callable[[QueuedEvent, Exception, str], Awaitable[str]]]
    ] = None
    chat: dc.InitVar[
        Optional[Callable[[str, Context], Awaitable[str]]]
    ] = None

    def __post_init__(self, name, aiohttp_app, format_command_result, format_command_error, chat) -> None:
        self.__dict__["_name"] = name
        self.__dict__["_aiohttp_app"] = aiohttp_app
        self.__dict__["_format_command_result"] = format_command_result
        self.__dict__["_format_command_error"] = format_command_error
        self.__dict__["_chat"] = chat
    
    @property
    def name(self) -> str:
        if self.__dict__["_name"]:
            return self.__dict__["_name"]
        return self.agent.name

    async def format_command_result(self, event: QueuedEvent, result: str) -> str:
        if self.__dict__["_format_command_result"]:
            return self.__dict__["_format_command_result"](event, result)
        return self.agent.format_command_result(event, result)

    async def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        if self.__dict__["_format_command_error"]:
            return self.__dict__["_format_command_error"](event, error, stack)
        return self.agent.format_command_error(event, error, stack)

    async def chat(self, message: str, ctx: Context) -> str:
        if self.__dict__["_chat"]:
            return self.__dict__["_chat"](message, ctx)
        return self.agent.chat(message, ctx)
