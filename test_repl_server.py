import asyncio

from sqlalchemy.ext.asyncio import create_async_engine

from ai_agent.agent import Runner, task_queue_empty
from ai_agent.agent_history import AgentHistoryService
from ai_agent.api import command
from ai_agent.default_command_parser import DefaultCommandParser
from ai_agent.event_bus import create_session
from ai_agent.interactive_chatter import InteractiveChatter
from ai_agent.models import Base
from ai_agent.modular_agent import ModularAgent, MessageFactory
from ai_agent.utils.aiohttp import serve_socket
from ai_agent.utils.blinker import iterate_signals
from ai_agent.utils.logging import setup_logging
from ai_agent.utils.sqlalchemy import merge_metadatas
from ai_agent.working_memory_service import WorkingMemoryService, Base as WorkingMemoryBase


@command
def echo(req, ctx):
    return ' '.join(req.args)


async def queue_messages(runner):
    ctx = runner.context()

    async for _ in iterate_signals(task_queue_empty, runner):
        event = await ctx.queue_agent("socket-test", "Nothing is running, please give another command")
        try:
            result = await ctx.wait_for_event(event)
            print("RESULT", result)
        except Exception as err:
            print("ERROR", err)


async def main() -> None:
    setup_logging(level="DEBUG")

    working_memory = WorkingMemoryService()
    agent_history = AgentHistoryService()

    engine = create_async_engine(
        "sqlite+aiosqlite:///agent.db",
        # echo=True
    )
    metadata = merge_metadatas(
        Base.metadata,
        working_memory.get_sqlalchemy_metadata(),
        agent_history.get_sqlalchemy_metadata(),
    )

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    session = await create_session("test-1", engine)

    socket_path = "./agent.sock"

    parser = DefaultCommandParser()

    agent = ModularAgent(
        "socket-test",
        InteractiveChatter(),
        message_providers=[
            MessageFactory(lambda ctx: "You are a secret agent", actor="system"),
            parser,
            working_memory.message_provider("socket-test"),
            agent_history.message_provider("socket-test"),
        ]
    )

    runner = Runner(
        session.session_id,
        engine,
        command_parser=parser,
        agents=[agent],
        agent_middlewares=[agent_history.middleware],
        commands=[echo, *working_memory.commands()]
    )

    async with serve_socket(runner.aiohttp_app, socket_path):
        print("Serving requests at", socket_path)

        task = asyncio.create_task(queue_messages(runner))

        await asyncio.gather(runner.run(), task)


if __name__ == "__main__":
    asyncio.run(main())
