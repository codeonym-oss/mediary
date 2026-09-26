"""Streams: what `Mediator.stream` returns, and how a stream's pipeline is layered."""

from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable
from contextlib import aclosing
from types import TracebackType
from typing import Any, TypeVar

_T_co = TypeVar("_T_co", covariant=True)

Open = Callable[[], AsyncGenerator[Any, None]]
"""Opens (the rest of) a stream's pipeline as an unstarted async generator."""


class Stream(AsyncIterator[_T_co]):
    """The items of a stream request, produced by its pipeline as they are iterated.

    Nothing runs until the first item is asked for: the handler is resolved and started then,
    and each further item is produced when the consumer asks for it.

    Iterate it once, with `async for`. To close the pipeline as soon as you stop, for instance
    after a `break` or an error, iterate it inside `async with`; this runs the `finally` blocks
    of its behaviors and handler at once, rather than whenever the stream is garbage-collected.

    Example:
        ```python
        async with mediator.stream(ExportOrders(since)) as orders:
            async for order in orders:
                if order.total > limit:
                    break  # the handler's cursor is closed when the block exits
        ```

    """

    __slots__ = ("_items",)

    def __init__(self, items: AsyncGenerator[_T_co, None]) -> None:
        """Wrap `items`, the outermost layer of the stream's pipeline."""
        self._items = items

    def __aiter__(self) -> "Stream[_T_co]":
        """Return the stream itself: it can be iterated only once."""
        return self

    async def __anext__(self) -> _T_co:
        """Return the next item, or raise `StopAsyncIteration` when the stream is done."""
        return await self._items.__anext__()

    async def aclose(self) -> None:
        """Stop the stream, running the cleanup of its behaviors and handler; idempotent."""
        await self._items.aclose()

    async def __aenter__(self) -> "Stream[_T_co]":
        """Return the stream, to be closed when the block exits."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the stream."""
        await self.aclose()


async def through(
    start: Callable[[], Awaitable[AsyncGenerator[Any, None]]],
) -> AsyncGenerator[Any, None]:
    """Yield the items of the generator `start()` returns, closing it when this closes."""
    async with aclosing(await start()) as items:
        async for item in items:
            yield item


async def layer(
    start: Callable[[Open], Awaitable[AsyncGenerator[Any, None]]], inner: Open
) -> AsyncGenerator[Any, None]:
    """Yield the items of a behavior started with `next`, which opens the `inner` layer.

    Every inner layer the behavior opens is closed when this closes, so closing the outermost
    layer closes the whole pipeline, however the behavior uses `next`.
    """
    opened: list[AsyncGenerator[Any, None]] = []

    def next() -> AsyncGenerator[Any, None]:
        opened.append(inner())
        return opened[-1]

    try:
        async with aclosing(through(lambda: start(next))) as items:
            async for item in items:
                yield item
    finally:
        for items in opened:
            await items.aclose()
