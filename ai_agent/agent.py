import abc
import asyncio
import bisect
import contextlib
import dataclasses as dc
import logging
import traceback
from datetime import datetime
from typing import List, Iterator, Optional, Dict, Tuple, Any, Callable

from sqlalchemy.ext.asyncio import AsyncEngine

from ai_agent.event_bus import EventBus, QueuedEvent, Event, event_queued


LOGGER = logging.getLogger(__name__)


class Context:
    """ """

    def __init__(
        self,
        engine: AsyncEngine,
        event_bus: EventBus,
        commands: List["Command"],
        get_event_future: Callable[[int], asyncio.Future],
        queue_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.engine = engine
        self.event_bus = event_bus
        self.queue_kwargs = queue_kwargs or {}
        self.get_event_future = get_event_future
        self.commands = commands

    def get_commands(self) -> List["Command"]:
        return self.commands

    async def queue_agent(
        self, agent: str, message: str, run_at: Optional[datetime] = None
    ) -> QueuedEvent:
        return await self.event_bus.queue_event(
            Event("agent", agent, {"message": message}), run_at=run_at, **self.queue_kwargs
        )

    async def queue_command(
        self,
        command: str,
        args: List[str],
        body: Optional[str] = None,
        run_at: Optional[datetime] = None,
    ) -> QueuedEvent:
        return await self.event_bus.queue_event(
            Event("command", command, {"args": args, "body": body}),
            run_at=run_at,
            **self.queue_kwargs,
        )

    async def wait_for_event(self, event_id: int) -> Optional[str]:
        event = await self.event_bus.get_event(event_id)
        if event.acknowledged:
            return event.result
        future = self.get_event_future(event_id)
        return await future


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


class Command(abc.ABC):
    """ """

    name: str

    def get_docs(self) -> CommandDocumentation:
        """ """
        return CommandDocumentation(self.name, self.name)

    def validate(self, args: List[str], body: Optional[str] = None) -> None:
        """ """

    @abc.abstractmethod
    async def __call__(self, cmd: CommandRequest, ctx: Context) -> Optional[str]:
        """ """
        raise NotImplementedError


# @dc.dataclass(frozen=True)
# class AgentMessage:
#     """ """

#     message: str
#     actor: str = "user"
#     level: str = "INFO"


# class MessageProvider(abc.ABC):
#     """ """

#     name: str

#     @abc.abstractmethod
#     async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
#         """ """
#         raise NotImplementedError


class CommandParser(abc.ABC):
    """ """

    @abc.abstractmethod
    def parse(self, result: str) -> Iterator[CommandRequest]:
        """ """
        raise NotImplementedError


class Agent(abc.ABC):
    """ """

    name: str

    @abc.abstractmethod
    def format_command_result(self, event: QueuedEvent, result: str) -> str:
        """ """
        raise NotImplementedError

    @abc.abstractmethod
    def format_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> str:
        """ """
        raise NotImplementedError

    @abc.abstractmethod
    async def chat(
        self,
        payload: AgentMessage,
        messages: List[AgentMessage] = (),
    ) -> str:
        """ """
        raise NotImplementedError


class Runner:
    """ """

    def __init__(
        self,
        command_parser: CommandParser,
        event_bus: EventBus,
        engine: AsyncEngine,
        agents: List[Agent] = (),
        commands: List[Command] = (),
        # message_providers: List[MessageProvider] = (),
    ) -> None:
        """ """
        self.command_parser = command_parser
        self.event_bus = event_bus
        self.engine = engine

        self.commands: Dict[str, Command] = {}
        self.agents: Dict[str, Agent] = {}
        self.message_providers: List[Tuple[MessageProvider, int]] = []

        for command in commands:
            self.register_command(command)

        # for idx, message_provider in enumerate(message_providers):
        #     self.register_message_provider(message_provider, order=idx)

        for agent in agents:
            self.register_agent(agent)

        self._event_futures: Dict[int, List[asyncio.Future]] = {}

    def register_command(self, command: Command) -> None:
        if command.name in self.commands:
            raise ValueError(f"'{command.name}' already registered")
        self.commands[command.name] = command

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self.agents:
            raise ValueError(f"'{agent.name}' already registered")
        self.agents[agent.name] = agent

    # def register_message_provider(
    #     self, message_provider: MessageProvider, order: float = float("inf")
    # ) -> None:
    #     bisect.insort(
    #         self.message_providers, (message_provider, order), key=lambda x: x[1]
    #     )
    
    def context(self, **kwargs) -> Context:

        def get_future(event_id):
            future = asyncio.Future()
            self._event_futures.setdefault(event_id, []).append(future)
            return future

        return Context(
            self.engine,
            self.event_bus,
            list(self.commands.values()),
            get_future,
            queue_kwargs=kwargs
        )

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

        ctx = self.context(source_event=event)
        messages = []

        for message_provider, _ in self.message_providers:
            messages.extend(message_provider.get_messages(agent_name, ctx))

        response = await agent.chat(
            AgentMessage(**event.payload),
            messages,
        )

        try:
            commands = list(self.command_parser.parse(response))
        except Exception as err:
            raise AgentResponseValidationError(response, "parsing", [err])

        errors = []
        for command in commands:
            try:
                if command.command not in self.commands:
                    raise InvalidCommand(command)
                self.commands[command.command].validate(command.args, command.body)
            except Exception as err:
                errors.append(CommandValidationError(command, err))

        if errors:
            raise AgentResponseValidationError(response, "validation", errors)

        for command in commands:
            await ctx.queue_command(command.command, command.args, command.body)

        return response

    async def _handle_command_event(self, event: QueuedEvent) -> Optional[str]:
        command_name = event.destination
        if command_name not in self.commands:
            raise InvalidCommand(command_name)
        command = self.commands[command_name]

        ctx = self.context(source_event=event)

        response = await command(
            CommandRequest(
                command=command_name,
                args=event.payload["args"],
                body=event.payload["body"],
            ),
            ctx,
        )

        if event.source_type == "agent" and response is not None:
            agent_name = event.source_destination
            if agent_name not in self.agents:
                raise InvalidAgent(agent_name)

            agent = self.agents[agent_name]
            await ctx.queue_agent(
                event.source_destination, agent.format_command_result(event, response)
            )

        return response

    async def _handle_agent_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> None:
        ctx = self.context(source_event=event)

        agent_name = event.destination
        if agent_name not in self.agents:
            raise InvalidAgent(agent_name)

        agent = self.agents[agent_name]

        await ctx.queue_agent(
            event.destination, agent.format_command_error(event, error, stack)
        )

    async def _handle_command_error(
        self, event: QueuedEvent, error: Exception, stack: str
    ) -> None:
        ctx = self.context(source_event=event)

        if event.source_type == "agent":
            agent_name = event.source_destination
            if agent_name not in self.agents:
                raise InvalidAgent(agent_name)

            agent = self.agents[agent_name]

            await ctx.queue_agent(
                agent_name, agent.format_command_error(event, error, stack)
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
        try:
            if event.type == "agent":
                result = await self._handle_agent_event(event)
                self._handle_event_result(event, result)
                return

            if event.type == "command":
                result = await self._handle_command_event(event)
                self._handle_event_result(event, result)
                return

            LOGGER.error(
                "Invalid event type %s:%s in event %d",
                event.type,
                event.destination,
                event.event_id,
            )
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
            if not events:
                return

            for event in events:
                event_map[event.event_id] = event
                if event.event_id in tasks:
                    continue
                task = asyncio.create_task(self._handle_event(event))
                tasks[event.event_id] = task
                reverse_tasks[id(task)] = event.event_id

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
        
        try:
            yield wait
        except asyncio.CancelledError:
            for task in tasks.values():
                task.cancel()

    async def _wait_for_events(self) -> None:
        future = asyncio.Future()

        @event_queued.connect_via(self.event_bus)
        def handler(_, event):
            nonlocal future
            future.set_result(event)

        try:
            while True:
                resolved = await future
                future = asyncio.Future()
                yield resolved
        finally:
            event_queued.disconnect(handler, self.event_bus)

    async def run(self, poll_interval: float = 1.0) -> None:
        events_gen = self._wait_for_events()

        wait_task = None
        event_task = None

        with self._task_waiter() as wait:
            while True:
                events = await self.event_bus.get_queued_events()
                if not events:
                    LOGGER.info(
                        "No pending messages found, sleeping for %.2fs", poll_interval
                    )
                    await asyncio.sleep(poll_interval)
                    continue
                
                if wait_task is not None:
                    wait_task.cancel()

                wait_task = asyncio.create_task(wait(events))
                
                if event_task is None:
                    event_task = asyncio.create_task(anext(events_gen))
                
                await asyncio.wait([wait_task, event_task], return_when=asyncio.FIRST_COMPLETED)

                if wait_task.done():
                    wait_task.result()
                    wait_task = None
                
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


class CommandValidationError(AIAgentError):
    """ """

    def __init__(self, command: str, message: str) -> None:
        self.command = command
        self.message = message
        super().__init__(f"Command {command} raised validation error: {message}")
