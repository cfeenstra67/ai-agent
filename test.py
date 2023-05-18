import asyncio
from typing import Optional

from sqlalchemy.ext.asyncio import create_async_engine

from ai_agent.agent import Runner, Command, CommandRequest, Context
from ai_agent.default_command_parser import DefaultCommandParser
from ai_agent.event_bus import create_session, EventBus
from ai_agent.models import Base
from ai_agent.utils.logging import setup_logging


class PingCommand(Command):

    name = "ping"

    async def __call__(self, cmd: CommandRequest, ctx: Context) -> Optional[str]:
        await asyncio.sleep(1)
        num = int(cmd.args[0]) if cmd.args else 0
        print("Ping", num)
        event = await ctx.queue_command("pong", [str(num + 1)])
        await ctx.wait_for_event(event.event_id)
        print("Ping 2", num)


class PongCommand(Command):

    name = "pong"

    async def __call__(self, cmd: CommandRequest, ctx: Context) -> Optional[str]:
        await asyncio.sleep(3)
        num = int(cmd.args[0]) if cmd.args else 0
        print("Pong", num)
        event = await ctx.queue_command("ping", [str(num + 1)])


async def main() -> None:
    setup_logging(level="DEBUG")

    engine = create_async_engine(
        "sqlite+aiosqlite:///agent.db",
        # echo=True
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session = await create_session("test-1", engine)

    event_bus = EventBus(engine, session.session_id)
    parser = DefaultCommandParser()

    runner = Runner(
        parser,
        event_bus,
        engine,
        commands=[
            PingCommand(),
            PongCommand()
        ],
        message_providers=[parser]
    )
    ctx = runner.context()

    event = await ctx.queue_command("ping", [])

    task = asyncio.create_task(runner.run())

    result = await ctx.wait_for_event(event.event_id)
    print("RESULT", result)

    await task


if __name__ == "__main__":
    asyncio.run(main())
