import dataclasses as dc
import inspect
import textwrap
from typing import Optional, Callable, Any, List, Coroutine, Union, Awaitable

from aiohttp import web

from ai_agent.agent import Command, CommandRequest, Context, CommandDocumentation, Agent
from ai_agent.event_bus import QueuedEvent
from ai_agent.modular_agent import AgentMessage, MessageProvider, CommandFilter
from ai_agent.utils.asyncio import maybe_await


@dc.dataclass(frozen=True)
class FunctionCommand(Command):
    """
    """
    name: str
    usage: str
    func: Callable[[CommandRequest, Context], Any]
    description: str
    long_description: str
    validate_func: Optional[Callable[[List[str], Optional[str]], Optional[int]]] = None

    def get_docs(self) -> CommandDocumentation:
        return CommandDocumentation(
            usage=self.usage,
            description=self.description,
            long_description=self.long_description,
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
    long_description: Optional[str] = None,
    validate: Optional[Callable[[List[str], Optional[str]], Optional[int]]] = None,
):
    def dec(f):
        f_name = name or f.__name__
        f_usage = usage or f_name
        f_description = description
        f_long_description = long_description
        if f_description is None and getattr(f, "__doc__", None):
            f_description = textwrap.dedent(f.__doc__).strip()
        elif f_description is None:
            f_description = f_usage
        
        if f_long_description is None:
            f_long_description = f_description

        f._cmd = FunctionCommand(
            name=f_name,
            usage=f_usage,
            description=f_description,
            func=f,
            validate_func=validate,
            long_description=f_long_description,
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
    func: dc.InitVar[Callable[[str, Context], Any]]
    default_actor: str = "user"

    def __post_init__(self, func) -> None:
        self.__dict__["_get_messages"] = func

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        
        def coerce_one(x):
            if isinstance(x, str):
                return AgentMessage(x, self.default_actor)
            return x

        result = await maybe_await(self.__dict__["_get_messages"](agent, ctx))
        result = coerce_one(result)

        if isinstance(result, AgentMessage):
            result = [result]
        elif isinstance(result, (list, tuple)) or inspect.isgenerator(result):
            result = list(map(coerce_one, result))
        else:
            raise TypeError(f"Invalid type for get_messages result: {type(result)}")
    
        return result


def message_provider(
    func: Optional[Callable[[Context], Coroutine[None, None, List[AgentMessage]]]] = None,
    *,
    default_actor: Optional[str] = None,
):
    def dec(f):
        kws = {}
        if default_actor is not None:
            kws["default_actor"] = default_actor

        f._msg_provider = FunctionMessageProvider(f, **kws)
        return f

    if func is None:
        return dec
    
    return dec(func)


def get_message_provider(obj: Any) -> MessageProvider:
    if isinstance(obj, MessageProvider):
        return obj
    if callable(obj) and isinstance(getattr(obj, "_msg_provider", None), MessageProvider):
        return obj._msg_provider
    if isinstance(obj, (str, AgentMessage)):
        return FunctionMessageProvider(lambda agent, ctx: obj)
    raise TypeError(f"Invalid message provider: {obj}")


@dc.dataclass(frozen=True)
class FunctionCommandFilter(CommandFilter):
    """
    """
    func: Callable[[List[Command]], List[Command]]

    def filter_commands(self, commands: List[Command]) -> List[Command]:
        return self.func(commands)


def command_filter(
    func: Optional[Callable] = None,
):
    def dec(f):
        func._cmd_filter = FunctionCommandFilter(f)
        return func

    if func is not None:
        return dec(func)

    return dec


def get_command_filter(obj: Any) -> CommandFilter:
    if isinstance(obj, CommandFilter):
        return obj
    if callable(obj) and isinstance(getattr(obj, "_cmd_filter", None), CommandFilter):
        return obj._cmd_filter
    raise TypeError(f"Invalid command filter: {obj}")


@dc.dataclass(frozen=True)
class AgentWrapper(Agent):
    """
    """
    agent: Agent
    new_name: Optional[str] = None
    new_aiohttp_app: Optional[
        Callable[..., web.Application | None]
    ] = None
    new_format_command_result: Optional[
        Callable[[QueuedEvent, str], Awaitable[str]]
    ] = None
    new_format_command_error: Optional[
        Callable[[QueuedEvent, Exception, str], Awaitable[str]]
    ] = None
    new_chat: Optional[
        Callable[[List[AgentMessage], Context], Awaitable[str]]
    ] = None
    new_get_messages: Optional[
        Callable[[str, Context], Awaitable[List[AgentMessage]]]
    ] = None
    new_filter_commands: Optional[
        Callable[[List[AgentMessage]], List[AgentMessage]]
    ] = None

    @property
    def name(self) -> str:
        if self.new_name:
            return self.new_name
        return self.agent.name

    async def format_command_result(self, event: QueuedEvent, result: str) -> str:
        if self.new_format_command_result:
            return await self.new_format_command_result(event, result)
        return await self.agent.format_command_result(event, result)

    async def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        if self.new_format_command_error:
            return await self.new_format_command_error(event, error, stack)
        return await self.agent.format_command_error(event, error, stack)

    def filter_commands(self, commands: List[AgentMessage]) -> List[AgentMessage]:
        if self.new_filter_commands:
            return self.new_filter_commands(commands)
        return self.agent.filter_commands(commands)

    async def get_messages(self, message: str, ctx: Context) -> List[AgentMessage]:
        if self.new_get_messages:
            return await self.new_get_messages(message, ctx)
        return await self.agent.get_messages(message, ctx)

    async def chat(self, messages: List[AgentMessage], ctx: Context) -> str:
        if self.new_chat:
            return await self.new_chat(messages, ctx)
        return await self.agent.chat(messages, ctx)
