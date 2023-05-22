import asyncio
import json
import logging
from typing import List

import aiohttp
from aiohttp import web

from ai_agent.modular_agent import Chatter, AgentMessage


LOGGER = logging.getLogger(__name__)


class InteractiveChatter(Chatter):
    """
    Use a unix socket to allow a human to emulate a chatter
    """
    def __init__(self) -> None:
        self.pending_messages = []
        self.message_available = asyncio.Event()
        self.lock = asyncio.Lock()

    async def _handle_ws(self, request: web.Request) -> web.Response:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        try:
            await asyncio.wait_for(self.lock.acquire(), 1)
        except asyncio.TimeoutError:
            await ws.send_json({"type": "locked"})
            return ws
        
        try:
            ws_gen = aiter(ws)

            tasks = set()
            tasks.add(asyncio.create_task(anext(ws_gen), name="ws_get"))
            tasks.add(asyncio.create_task(self.message_available.wait(), name="msg_get"))
            should_break = False

            while not should_break:
                if not tasks:
                    raise RuntimeError("No tasks to process. This is unexpected")

                done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                
                for task in done:
                    name = task.get_name()
                    if name == "ws_get":
                        tasks.add(asyncio.create_task(anext(ws_gen), name="ws_get"))
                        try:
                            msg = task.result()
                        except StopAsyncIteration:
                            should_break = True
                            break

                        if msg.type != aiohttp.WSMsgType.TEXT:
                            LOGGER.warn("Unhandled message type in %s", msg)
                            continue

                        data = json.loads(msg.data)
                        if self.message_available.is_set():
                            future, _ = self.pending_messages.pop(0)
                            future.set_result(data["message"])
                            if not self.pending_messages:
                                self.message_available.clear()
                            tasks.add(asyncio.create_task(self.message_available.wait(), name="msg_get"))
                        else:
                            LOGGER.warn(
                                "Received message when not waiting "
                                "on a response, unexpected. No action taken"
                            )
                        
                        continue

                    if name == "msg_get":
                        messages = self.pending_messages[0][1]
                        await ws.send_json({
                            "type": "message",
                            "messages": [
                                {"message": message.message, "actor": message.actor}
                                for message in messages
                            ]
                        })

                        continue
                        
                    LOGGER.warn("Unhandled task name in web socket: %s", name)

            return ws
        finally:
            self.lock.release()

    def aiohttp_app(self):
        app = web.Application()
        app.add_routes([web.get("/chat", self._handle_ws)])
        return app

    async def chat(self, messages: List[AgentMessage]) -> str:
        future = asyncio.Future()
        self.pending_messages.append((future, messages))
        self.message_available.set()
        return await future
