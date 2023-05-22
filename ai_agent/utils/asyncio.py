import inspect
from typing import TypeVar, Awaitable, Union


T  = TypeVar("T")


async def maybe_await(obj: Union[T, Awaitable[T]]) -> T:
    if inspect.isawaitable(obj):
        return await obj
    return obj
