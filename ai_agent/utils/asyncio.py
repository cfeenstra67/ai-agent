import asyncio
import inspect
import logging
from typing import TypeVar, Awaitable, Union, Optional, AsyncGenerator, Tuple, Callable


T  = TypeVar("T")

LOGGER = logging.getLogger(__name__)


async def maybe_await(obj: Union[T, Awaitable[T]]) -> T:
    if inspect.isawaitable(obj):
        return await obj
    return obj


def log_errors_cb(task: asyncio.Task, logger: Optional[logging.Logger] = None) -> None:
    if logger is None:
        logger = LOGGER
    try:
        task.result()
    except Exception:
        task.print_stack()
        logger.exception("Error encountered in %s", task)


def peekable_gen(gen: AsyncGenerator[T, None]) -> Tuple[
    AsyncGenerator[T, None],
    Callable[[], Awaitable[T]]
]:
    next_task = asyncio.create_task(anext(gen))

    async def wrapped_gen():
        nonlocal next_task
        while True:
            result = await next_task
            next_task = asyncio.create_task(anext(gen))
            yield result
    
    async def peek():
        return await next_task
    
    return wrapped_gen(), peek
