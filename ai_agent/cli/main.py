import asyncio
import json
from typing import Optional

import aiohttp
import click
from aioconsole import ainput, aprint
from sqlalchemy.ext.asyncio import create_async_engine

from ai_agent.agent import Runner
from ai_agent.event_bus import create_session, get_session
from ai_agent.models import Base
from ai_agent.utils.aiohttp import serve_socket
from ai_agent.utils.asyncio import maybe_await, peekable_gen
from ai_agent.utils.click import async_command
from ai_agent.utils.fun_name import get_fun_name
from ai_agent.utils.importlib import import_module
from ai_agent.utils.logging import setup_logging


@click.group()
@click.option(
    "-d", "--db",
    default="./agent.db",
    help="Path of a database file to use"
)
@click.option(
    "-l", "--log-level",
    default="INFO",
    help="Log level"
)
@click.pass_context
def cli(ctx, db: str, log_level: str):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db}",
    )
    setup_logging(level=log_level.upper().strip())

    ctx.obj = {"engine": engine}


socket_option = click.option(
    "-x", "--socket",
    default="./agent.sock",
    help="Socket to attach to"
)

@async_command(cli)
@click.pass_context
@click.argument("runner_path")
@click.option("-n", "--new-session", is_flag=True)
@click.option("--name", default=None)
@click.option("-s", "--session-id", type=int, default=None)
@socket_option
async def run(ctx, runner_path: str, socket: str, session_id: Optional[int], new_session: bool, name: str):
    """
    """
    if session_id is not None and new_session:
        click.secho(
            "-s/--session-id and -n/--new-session should not both "
            "be passed",
            fg="red"
        )
        raise click.Abort
    if session_id is None and not new_session:
        click.secho("-s/--session-id or -n/--new-session must be passed", fg="red")
        raise click.Abort

    engine = ctx.obj["engine"]

    module = import_module(runner_path, "__main__")

    handler = getattr(module, "runner", None)
    if handler is None:
        click.secho(f"No `handler` function found in {runner_path}", fg="red")
        raise click.Abort

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    created = False
    if session_id is not None:
        session = await get_session(session_id, engine)
        click.secho(
            f"Session retrieved. Name: {session.name}. "
            f"ID: {session.session_id}",
            fg="green",
            bold=True
        )
    else:
        session_name = name or get_fun_name()
        session = await create_session(
            session_name,
            engine
        )
        created = True
        click.secho(
            f"Session created. Name: {session_name}. "
            f"ID: {session.session_id}",
            fg="green",
            bold=True
        )

    runner, *coros = await maybe_await(handler(session.session_id, engine, created))

    if not isinstance(runner, Runner):
        click.secho(f"Invalid response from handler in {runner_path}: {runner}")
        raise click.Abort

    async with serve_socket(runner.aiohttp_app, socket):
        print("Serving requests at", socket)
        await asyncio.gather(runner.run(), *coros)


@async_command(cli)
@click.argument("agent")
@socket_option
async def attach(agent: str, socket: str):
    connector = aiohttp.UnixConnector(path=socket)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.ws_connect(f"http://runner/agents/{agent}/chat", timeout=0.5) as ws:
            await aprint(click.style(f"Connected to {socket}", fg="green", bold=True))
            ws_gen, peek = peekable_gen(ws)

            async for message in ws_gen:
                if message.type == aiohttp.WSMsgType.TEXT:
                    response = json.loads(message.data)
                    if response["type"] == "locked":
                        await aprint("Another client is already connected")
                        break

                    if response["type"] == "message":
                        msg_str = "\n\n".join(
                            f"{click.style(msg['actor'], fg='yellow', bold=True)}:\n{msg['message']}"
                            for msg in response["messages"]
                        )
                        await aprint(msg_str)
                        peek_task = asyncio.create_task(peek())
                        input_task = asyncio.create_task(ainput(click.style("\nYour response: ", fg='green', bold=True)))

                        await asyncio.wait([peek_task, input_task], return_when=asyncio.FIRST_COMPLETED)

                        if peek_task.done():
                            try:
                                peek_task.result()
                            except StopAsyncIteration:
                                await aprint(
                                    "\nServer Connection closed. Exiting"
                                )
                                break

                        result = await input_task
                        await aprint()
                        if result.strip() == "exit":
                            await aprint("Exiting")
                            break

                        await ws.send_json({"message": result})
                        continue

                    await aprint("Unhandled message type", response["type"])
                elif message.type == aiohttp.WSMsgType.CLOSE:
                    await aprint("CLOSING", message)
                    break
                elif message.type == aiohttp.WSMsgType.ERROR:
                    await aprint("ERROR", message)
                    break


@async_command(cli)
@socket_option
async def tail(socket: str):
    connector = aiohttp.UnixConnector(path=socket)
    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.ws_connect(f"http://runner/event-bus/tail", timeout=0.5) as ws:
            async for message in ws:
                if message.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(message.data)
                    click.echo(f"{click.style('Type', fg='green', bold=True)}: {data['type']}")
                    click.echo(f"{click.style('Destination', fg='green', bold=True)}: {data['destination']}")
                    click.echo(f"{click.style('Result', fg='green', bold=True)}:\n{data['result']}")
                    print()
                elif message.type == aiohttp.WSMsgType.CLOSE:
                    print("CLOSING", message)
                    break
                elif message.type == aiohttp.WSMsgType.ERROR:
                    print("ERROR", message)
                    break
