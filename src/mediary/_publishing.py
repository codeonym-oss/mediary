"""Publish strategies: how the handlers of one notification are run."""

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

NotificationHandler = Callable[[], Awaitable[Any]]
"""Runs one handler of the notification being published."""


class PublishStrategy(Protocol):
    """Runs the handlers of a notification, in `Mediator.publish`.

    Handlers are given in a deterministic order: by fully qualified name.
    """

    async def publish(self, handlers: Sequence[NotificationHandler], /) -> None:
        """Run `handlers`."""
        ...


class Sequential:
    """Run handlers one after another; the first error stops the rest and propagates."""

    async def publish(self, handlers: Sequence[NotificationHandler], /) -> None:
        """Await each handler in turn."""
        for run in handlers:
            await run()


class Concurrent:
    """Run all handlers concurrently in an `asyncio.TaskGroup`.

    Every handler runs to completion even if others fail; failures are then raised together
    as an `ExceptionGroup`, in handler order.
    """

    async def publish(self, handlers: Sequence[NotificationHandler], /) -> None:
        """Run the handlers as tasks and wait for all of them."""
        errors: list[Exception | None] = [None] * len(handlers)

        async def run(index: int) -> None:
            try:
                await handlers[index]()
            except Exception as exc:
                errors[index] = exc

        async with asyncio.TaskGroup() as group:
            for index in range(len(handlers)):
                group.create_task(run(index))
        failures = [error for error in errors if error is not None]
        if failures:
            raise ExceptionGroup(f"{len(failures)} notification handler(s) failed", failures)
