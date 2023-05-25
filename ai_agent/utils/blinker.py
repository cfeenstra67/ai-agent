import asyncio
import inspect
import logging
from functools import wraps
from typing import Any, AsyncGenerator, Optional

import blinker


LOGGER = logging.getLogger(__name__)


def wait_for_signal(signal: blinker.Signal, sender: Any = blinker.ANY) -> asyncio.Future:
    future = asyncio.Future()

    def handle_signal(sender, **kwargs):
        future.set_result((sender, kwargs))
        signal.disconnect(handle_signal, sender)

    signal.connect(handle_signal, sender)
    
    return future


async def iterate_signals(signal: blinker.Signal, sender: Any = blinker.ANY) -> AsyncGenerator:    
    queue = asyncio.Queue()

    def handle_signal(sender, **kwargs):
        queue.put_nowait((sender, kwargs))
    
    signal.connect(handle_signal, sender)

    try:
        while True:
            yield await queue.get()
    finally:
        signal.disconnect(handle_signal, sender)


def connect_async(signal: blinker.Signal, sender: Any = blinker.ANY, loop: Optional[asyncio.AbstractEventLoop] = None):
    if loop is None:
        loop = asyncio.get_event_loop()
    
    def dec(f):

        def done_cb(future):
            try:
                future.result()
            except Exception:
                LOGGER.exception(
                    "%s handler: %s raised exception",
                    signal,
                    getattr(f, "__name__", f)
                )

        @signal.connect_via(sender)
        @wraps(f)
        def handler(*args, **kwargs):
            result = f(*args, **kwargs)
            if inspect.iscoroutine(result):
                task = loop.create_task(result)
                task.add_done_callback(done_cb)
                return task
            return result
        
        return handler

    return dec
