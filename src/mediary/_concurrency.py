"""Sleeping, timeouts, task groups and worker threads on the running event loop.

Under asyncio these use the standard library alone. Under any other event loop, such as trio,
they use AnyIO, which the ``mediary[anyio]`` extra installs.
"""

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from typing import Any, TypeVar

_T = TypeVar("_T")


def _on_asyncio() -> bool:
    # Trio, and every event loop AnyIO supports, say they are running through sniffio, which
    # they import. Asyncio doesn't, so without sniffio loaded, only asyncio can be running.
    sniffio = sys.modules.get("sniffio")
    if sniffio is not None:
        try:
            return sniffio.current_async_library() == "asyncio"
        except sniffio.AsyncLibraryNotFoundError:
            return False
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _anyio() -> Any:
    try:
        import anyio
    except ImportError:
        raise ModuleNotFoundError(
            "mediary needs AnyIO to run on an event loop other than asyncio, such as trio: "
            "pip install mediary[anyio]",
            name="anyio",
        ) from None
    return anyio


async def sleep(seconds: float) -> None:
    """Sleep for ``seconds`` on the running event loop."""
    if _on_asyncio():
        await asyncio.sleep(seconds)
    else:
        await _anyio().sleep(seconds)


async def run_sync(fn: Callable[..., _T], *args: Any) -> _T:
    """Return ``fn(*args)``, called on a worker thread so it never blocks the event loop.

    Cancelling the caller doesn't stop the thread: it is abandoned and runs to completion in the
    background, and its result is dropped.
    """
    if _on_asyncio():
        return await asyncio.to_thread(fn, *args)
    return await _anyio().to_thread.run_sync(partial(fn, *args), abandon_on_cancel=True)


class Expired(Exception):
    """The time limit of ``within`` ran out, and the awaited work was cancelled."""


async def within(seconds: float, work: Callable[[], Awaitable[_T]]) -> _T:
    """Return ``await work()``, or cancel it and raise ``Expired`` after ``seconds``.

    A ``TimeoutError`` raised by ``work`` itself propagates unchanged.
    """
    if _on_asyncio():
        deadline = asyncio.timeout(seconds)
        try:
            async with deadline:
                return await work()
        except TimeoutError as exc:
            if deadline.expired():
                raise Expired from exc
            raise
    with _anyio().move_on_after(seconds):
        return await work()
    raise Expired  # the block only ends without returning when the time ran out


async def run_all(
    jobs: Sequence[Callable[[], Awaitable[object]]], limit: int | None = None
) -> list[Exception | None]:
    """Run ``jobs`` concurrently until all of them finish; return each one's error, or None.

    At most ``limit`` run at once (all of them when None): that many tasks each take the next
    job, in order, until none is left.
    """
    errors: list[Exception | None] = [None] * len(jobs)
    pending = iter(range(len(jobs)))

    async def work() -> None:
        for index in pending:  # shared, so each job runs once, on whichever task is free
            try:
                await jobs[index]()
            except Exception as exc:
                errors[index] = exc

    workers = len(jobs) if limit is None else min(limit, len(jobs))
    if _on_asyncio():
        async with asyncio.TaskGroup() as group:
            for _ in range(workers):
                group.create_task(work())
    else:
        async with _anyio().create_task_group() as group:
            for _ in range(workers):
                group.start_soon(work)
    return errors
