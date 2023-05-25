import abc
import asyncio
import contextlib
import dataclasses as dc
import logging
import traceback
from datetime import datetime
from typing import List, Iterator, Optional, Dict, Any, Callable, Union, Awaitable

from aiohttp import web
from blinker import signal
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from ai_agent.event_bus import EventBus, QueuedEvent, Event, event_queued, event_bus_aiohttp_app, DEFAULT_PRIORITY
from ai_agent.utils.blinker import iterate_signals
from ai_agent.utils.aiohttp import aiohttp_error_handler_middleware
from ai_agent.utils.asyncio import maybe_await


LOGGER = logging.getLogger(__name__)

task_queue_empty = signal("task-queue-empty")


class Context:
    """ """
    event_id: Optional[int]

    def __init__(
        self,
        session_id: int,
        engine: AsyncEngine,
        event_bus: EventBus,
        get_commands: Callable[[Optional[str]], List["Command"]],
        get_event_future: Callable[[int], asyncio.Future],
        event: Optional[QueuedEvent] = None,
    ) -> None:
        self.session_id = session_id
        self.engine = engine
        self.event = event
        self.event_id = event and event.event_id
        self._event_bus = event_bus
        self._get_commands = get_commands
        self._get_event_future = get_event_future
        self.Session = async_sessionmaker(bind=engine)

    async def queue_agent(
        self, agent: str, message: str, *, run_at: Optional[datetime] = None, priority: int = DEFAULT_PRIORITY
    ) -> QueuedEvent:
        return await self._event_bus.queue_event(
            Event("agent", agent, {"message": message}, priority),
            run_at=run_at,
            source_event=self.event
        )

    async def queue_command(
        self,
        command: str,
        args: List[str],
        body: Optional[str] = None,
        *,
        run_at: Optional[datetime] = None,
        priority: int = DEFAULT_PRIORITY,
    ) -> QueuedEvent:
        return await self._event_bus.queue_event(
            Event("command", command, {"args": args, "body": body}, priority),
            run_at=run_at,
            source_event=self.event,
        )

    async def get_event_history(
        self,
        type: str,
        destination: str,
        limit: int,
    ) -> List[QueuedEvent]:
        return await self._event_bus.get_event_history(
            type,
            destination,
            limit,
        )

    async def wait_for_event(self, event: Union[QueuedEvent, int]) -> Optional[str]:
        if isinstance(event, QueuedEvent):
            event = event.event_id

        event_obj = await self._event_bus.get_event(event)
        if event_obj.acknowledged:
            return event_obj.result
        future = self._get_event_future(event)
        return await future

    def get_commands(self, agent: Optional[str] = None) -> List["Command"]:
        return self._get_commands(agent)

    @contextlib.asynccontextmanager
    async def session_ctx(self):
        async with self.Session() as session:
            yield session


@dc.dataclass(frozen=True)
class CommandRequest:
    """ """

    command: str
    args: List[str]
    body: Optional[str] = None


@dc.dataclass(frozen=True)
class CommandDocumentation:
    """ """

    usage: str
    description: str
    long_description: str


class Command(abc.ABC):
    """ """

    name: str

    def get_docs(self) -> CommandDocumentation:
        """ """
        return CommandDocumentation(self.name, self.name, self.name)

    def validate(self, args: List[str], body: Optional[str] = None) -> Optional[int]:
        """
        Validate the message. Optionally return a priority
        """

    @abc.abstractmethod
    async def __call__(self, cmd: CommandRequest, ctx: Context) -> Optional[str]:
        """ """
        raise NotImplementedError


class CommandParser(abc.ABC):
    """ """

    @abc.abstractmethod
    def parse(self, result: str) -> Iterator[CommandRequest]:
        """ """
        raise NotImplementedError
    

@dc.dataclass(frozen=True)
class AgentMessage:
    """ """

    message: str
    actor: str = "user"


class Agent(abc.ABC):
    """ """

    name: str

    def aiohttp_app(self) -> Optional[web.Application]:
        """
        """
        return None

    @abc.abstractmethod
    async def format_command_result(self, event: QueuedEvent, result: str) -> str:
        """ """
        raise NotImplementedError

    @abc.abstractmethod
    async def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        """ """
        raise NotImplementedError

    @abc.abstractmethod
    def filter_commands(self, commands: List[Command]) -> List[Command]:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def get_messages(self, message: str, ctx: Context) -> List[AgentMessage]:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def chat(self, messages: List[AgentMessage], ctx: Context) -> str:
        """ """
        raise NotImplementedError


EventPrioritizer = Callable[
    [List[QueuedEvent]],
    Union[List[QueuedEvent], Awaitable[List[QueuedEvent]]]
]

AgentMiddleware = Callable[
    [Agent, Context],
    Union[Agent, Awaitable[Agent]]
]


class Runner:
    """ """

    def __init__(
        self,
        session_id: int,
        engine: AsyncEngine,
        agents: List[Agent] = (),
        agent_middlewares: List[AgentMiddleware] = (),
        commands: List[Command] = (),
        command_parser: Optional[CommandParser] = None,
        event_bus: Optional[EventBus] = None,
        prioritizer: Optional[EventPrioritizer] = None,
        aiohttp_app: Optional[web.Application] = None,
    ) -> None:
        """ """
        if event_bus is None:
            event_bus = EventBus(engine, session_id)

        if command_parser is None:
            from ai_agent.default_command_parser import DefaultCommandParser
            command_parser = DefaultCommandParser()
        
        if aiohttp_app is None:
            aiohttp_app = web.Application(
                middlewares=[aiohttp_error_handler_middleware]
            )
        
        if prioritizer is None:
            from ai_agent.prioritizers import default_prioritizer
            prioritizer = default_prioritizer

        self.session_id = session_id
        self.engine = engine
        self.agent_middlewares = agent_middlewares
        self.command_parser = command_parser
        self.event_bus = event_bus
        self.prioritizer = prioritizer
        self.aiohttp_app = aiohttp_app
        
        self.aiohttp_app.add_subapp(
            "/event-bus",
            event_bus_aiohttp_app(event_bus)
        )

        self.commands: Dict[str, Command] = {}
        self.agents: Dict[str, Agent] = {}

        for command in commands:
            self.register_command(command)

        for agent in agents:
            self.register_agent(agent)

        self._event_futures: Dict[int, List[asyncio.Future]] = {}

    def register_command(self, command: Command) -> None:
        from ai_agent.api import get_command

        command = get_command(command)
        if command.name in self.commands:
            raise ValueError(f"'{command.name}' already registered")
        self.commands[command.name] = command

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self.agents:
            raise ValueError(f"'{agent.name}' already registered")
        self.agents[agent.name] = agent
        
        app = agent.aiohttp_app()
        if app is not None:
            self.aiohttp_app.add_subapp(f"/agents/{agent.name}", app)

    def context(self, event: Optional[QueuedEvent] = None) -> Context:

        def get_future(event_id):
            future = asyncio.Future()
            self._event_futures.setdefault(event_id, []).append(future)
            return future

        return Context(
            self.session_id,
            self.engine,
            self.event_bus,
            self._get_commands,
            get_future,
            event=event
        )

    def _get_commands(self, agent: Optional[str]) -> List[Command]:
        all_commands = list(self.commands.values())
        if agent is None:
            return all_commands
        if agent not in self.agents:
            raise InvalidAgent(agent)
        agent_obj = self.agents[agent]
        return agent_obj.filter_commands(all_commands)

    def _handle_event_result(self, event: QueuedEvent, result: str) -> None:
        for future in self._event_futures.pop(event.event_id, []):
            future.set_result(result)

    def _handle_event_error(self, event: QueuedEvent, error: Exception) -> None:
        for future in self._event_futures.pop(event.event_id, []):
            future.set_exception(error)

    async def _handle_agent_event(self, event: QueuedEvent) -> str:
        agent_name = event.destination
        if agent_name not in self.agents:
            raise InvalidAgent(agent_name)
        agent = self.agents[agent_name]

        ctx = self.context(event)

        for middleware in self.agent_middlewares:
            agent = await maybe_await(middleware(agent, ctx))

        messages = await agent.get_messages(event.payload["message"], ctx)
        response = await agent.chat(messages, ctx)
        yield response

        try:
            commands = list(self.command_parser.parse(response))
        except Exception as err:
            raise AgentResponseValidationError(response, "parsing", [err])

        agent_commands = {
            cmd.name: cmd
            for cmd in self._get_commands(agent_name)
        }

        errors = []
        priorities = []
        for command in commands:
            try:
                if command.command not in agent_commands:
                    raise InvalidCommand(command.command)
                priority = agent_commands[command.command].validate(command.args, command.body)
                if priority is None:
                    priority = DEFAULT_PRIORITY
                priorities.append(priority)
            except Exception as err:
                errors.append(CommandValidationError(command, err))

        if errors:
            raise AgentResponseValidationError(response, "validation", errors)

        for command, priority in zip(commands, priorities):
            await ctx.queue_command(command.command, command.args, command.body, priority=priority)

    async def _handle_command_event(self, event: QueuedEvent) -> Optional[str]:
        command_name = event.destination
        if command_name not in self.commands:
            raise InvalidCommand(command_name)
        command = self.commands[command_name]

        ctx = self.context(event)

        response = await command(
            CommandRequest(
                command=command_name,
                args=event.payload["args"],
                body=event.payload["body"],
            ),
            ctx,
        )
        yield response

        if event.source_type == "agent" and response is not None:
            agent_name = event.source_destination
            if agent_name not in self.agents:
                raise InvalidAgent(agent_name)

            agent = self.agents[agent_name]
            await ctx.queue_agent(
                event.source_destination, await agent.format_command_result(event, response)
            )

    async def _handle_agent_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> None:
        ctx = self.context(event)

        agent_name = event.destination
        if agent_name not in self.agents:
            raise InvalidAgent(agent_name)

        agent = self.agents[agent_name]

        await ctx.queue_agent(
            event.destination, await agent.format_command_error(event, error, stack),
            priority=DEFAULT_PRIORITY + 1
        )

    async def _handle_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> None:
        ctx = self.context(event)

        if event.source_type == "agent":
            agent_name = event.source_destination
            if agent_name not in self.agents:
                raise InvalidAgent(agent_name)

            agent = self.agents[agent_name]

            await ctx.queue_agent(
                agent_name, await agent.format_command_error(event, error, stack),
                priority=DEFAULT_PRIORITY + 1
            )

    async def _handle_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> None:
        try:
            if event.type == "agent":
                await self._handle_agent_error(event, error, stack)
                return

            if event.type == "command":
                await self._handle_command_error(event, error, stack)
                return
        except Exception:
            LOGGER.exception(
                "Error encountered handling error for event %d (%s:%s)",
                event.event_id,
                event.type,
                event.destination,
            )

    async def _handle_event(self, event: QueuedEvent) -> None:
        LOGGER.debug(
            "Handling event %d (%s:%s)", event.event_id, event.type, event.destination
        )

        result = None
        stack = None
        cancelled = False
        try:
            if event.type == "agent":
                async for response in self._handle_agent_event(event):
                    result = response
                self._handle_event_result(event, result)
                print("HANDLE RESULT")
                return

            if event.type == "command":
                async for response in self._handle_command_event(event):
                    result = response
                self._handle_event_result(event, result)
                return

            LOGGER.error(
                "Invalid event type %s:%s in event %d",
                event.type,
                event.destination,
                event.event_id,
            )
        except asyncio.CancelledError:
            cancelled = True
            raise
        except Exception as err:
            stack = traceback.format_exc()
            LOGGER.exception(
                "Error encountered handling event %d (%s:%s)",
                event.event_id,
                event.type,
                event.destination,
            )
            await self._handle_error(event, err, stack)
            self._handle_event_error(event, err)
        finally:
            if not cancelled:
                await self.event_bus.ack_event(
                    event.event_id,
                    event.type,
                    event.destination,
                    result=result,
                    error=stack,
                )

    @contextlib.contextmanager
    def _task_waiter(self):
        tasks = {}
        event_map = {}
        reverse_tasks = {}

        async def wait(events: List[QueuedEvent]) -> None:
            for event in events:
                event_map[event.event_id] = event
                if event.event_id in tasks:
                    continue

                task = asyncio.create_task(self._handle_event(event))
                tasks[event.event_id] = task
                reverse_tasks[id(task)] = event.event_id
            
            if not tasks:
                return True

            done, _ = await asyncio.shield(asyncio.wait(
                list(tasks.values()), return_when=asyncio.FIRST_COMPLETED
            ))
            for task in done:
                event_id = reverse_tasks.pop(id(task))
                tasks.pop(event_id, None)
                event = event_map.pop(event_id)

                try:
                    task.result()
                    LOGGER.debug("Event %d finished", event_id)
                except Exception:
                    LOGGER.exception(
                        "Unexpected error when handling event %d", event_id
                    )
            
            return False

        try:
            yield wait
        except asyncio.CancelledError:
            for task in tasks.values():
                task.cancel()
            raise

    async def _wait_for_events(self) -> None:
        async for _, kwargs in iterate_signals(event_queued, self.event_bus):
            yield kwargs["event"]

    async def run(self) -> None:
        events_gen = self._wait_for_events()

        wait_task = None
        event_task = None

        with self._task_waiter() as wait:
            while True:
                events = await self.event_bus.get_queued_events()
                if events:
                    events = await maybe_await(self.prioritizer(events))
                else:
                    task_queue_empty.send(self)

                if wait_task is not None:
                    wait_task.cancel()

                wait_task = asyncio.create_task(wait(events))
                
                if event_task is None:
                    event_task = asyncio.create_task(anext(events_gen))
                
                await asyncio.wait([wait_task, event_task], return_when=asyncio.FIRST_COMPLETED)

                empty = False
                if wait_task.done():
                    empty = wait_task.result()
                    wait_task = None
                
                if empty and not event_task.done():
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(asyncio.shield(event_task), 5)

                if event_task.done():
                    event_task.result()
                    event_task = None


class AIAgentError(Exception):
    """ """


class CommandValidationError(AIAgentError):
    """ """

    def __init__(self, command: CommandRequest, error: Exception) -> None:
        self.command = command
        self.error = error
        super().__init__(
            f"Validation failed for {command} with error: "
            f"{type(error).__name__}: {error}"
        )


class AgentResponseValidationError(Exception):
    """ """

    def __init__(self, response: str, stage: str, errors: List[Exception]) -> None:
        self.errors = errors
        self.stage = stage
        errors_str = "\n".join([f"{type(error).__name__}: {error}" for error in errors])

        super().__init__(
            f"Failed to parse the following response in stage {stage}:"
            f"\n{response}\n\nErrors:\n{errors_str}"
        )


class InvalidAgent(AIAgentError):
    """ """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Invalid agent: {name}")


class InvalidCommand(AIAgentError):
    """ """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Invalid command: {name}")
