import contextlib
import logging
import os
from typing import AsyncContextManager, Callable, Awaitable

from aiohttp import web

from ai_agent.utils.os import socket_exists


LOGGER = logging.getLogger(__name__)


async def aiohttp_error_handler_middleware(
    app: web.Application,
    handler: Callable[[web.Request], Awaitable[web.Response]]
) -> Callable[[web.Request], Awaitable[web.Response]]:

    async def wrapper(request: web.Request) -> web.Response:
        try:
            return await handler(request)
        except web.HTTPException as err:
            return web.json_response(
                {"status": err.status, "message": str(err)},
                status=err.status
            )
        except Exception:
            LOGGER.exception("Error handling %s", request.path)
            return web.json_response(
                {"status": 500, "message": "Internal server error"},
                status=500,
            )
    
    return wrapper


@contextlib.asynccontextmanager
async def serve_socket(app: web.Application, socket_path: str) -> AsyncContextManager[web.Application]:
    """
    """
    if socket_exists(socket_path):
        raise RuntimeError(f"Socket exists: {socket_path}")

    runner = web.AppRunner(app, handle_signals=True)
    await runner.setup()

    site = web.UnixSite(runner, socket_path)
    await site.start()

    try:
        yield
    finally:
        await runner.cleanup()
        if socket_exists(socket_path):
            os.remove(socket_path)
