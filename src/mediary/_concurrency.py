"""Sleeping, timeouts and task groups on the running event loop: asyncio, or AnyIO's backends.

Under asyncio these use the standard library alone. Under any other event loop, such as trio,
they use AnyIO, which the `mediary[anyio]` extra installs.
"""

import asyncio
import sys
from collections.abc import Awaitable, Callable, Sequence
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
    """Sleep for `seconds` on the running event loop."""
    if _on_asyncio():
        await asyncio.sleep(seconds)
    else:
        await _anyio().sleep(seconds)


class Expired(Exception):
    """The time limit of `within` ran out, and the awaited work was cancelled."""


async def within(seconds: float, work: Callable[[], Awaitable[_T]]) -> _T:
    """Return `await work()`, or cancel it and raise `Expired` after `seconds`.

    A `TimeoutError` raised by `work` itself propagates unchanged.
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


async def run_all(jobs: Sequence[Callable[[], Awaitable[object]]]) -> list[Exception | None]:
    """Run `jobs` concurrently until all of them finish; return each one's error, or None."""
    errors: list[Exception | None] = [None] * len(jobs)

    async def run(index: int) -> None:
        try:
            await jobs[index]()
        except Exception as exc:
            errors[index] = exc

    if _on_asyncio():
        async with asyncio.TaskGroup() as group:
            for index in range(len(jobs)):
                group.create_task(run(index))
    else:
        async with _anyio().create_task_group() as group:
            for index in range(len(jobs)):
                group.start_soon(run, index)
    return errors
