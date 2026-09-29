"""Publish strategies: how the handlers of one notification are run."""

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from ._concurrency import run_all


@dataclass(frozen=True, slots=True, eq=False)
class NotificationCall:
    """One handler of the notification being published, for a ``PublishStrategy`` to run.

    ``await call()`` runs the handler; its result, if any, is discarded. ``handler`` is the
    handler as it was registered (a function or a class) and ``notification`` the notification,
    so a strategy can log, isolate or throttle each handler.

    Example:
        .. code-block:: python

            class LogFailures:
                async def publish(self, calls: Sequence[NotificationCall], /) -> None:
                    for call in calls:
                        try:
                            await call()
                        except Exception:
                            log.exception("%r failed on %r", call.handler, call.notification)

    """

    handler: Any
    notification: object
    run: Callable[[], Awaitable[object]] = field(repr=False)

    async def __call__(self) -> None:
        """Run the handler on the notification."""
        await self.run()


class PublishStrategy(Protocol):
    """Runs the handlers of a notification, in ``Mediator.publish``.

    Handlers are given in a deterministic order: by fully qualified name.
    """

    async def publish(self, calls: Sequence[NotificationCall], /) -> None:
        """Run each of ``calls``."""
        ...


class Sequential:
    """Run handlers one after another; the first error stops the rest and propagates."""

    async def publish(self, calls: Sequence[NotificationCall], /) -> None:
        """Await each handler in turn."""
        for call in calls:
            await call()


class Concurrent:
    """Run all handlers concurrently, in a task group.

    Every handler runs to completion even if others fail; failures are then raised together
    as an ``ExceptionGroup``, in handler order. It runs on asyncio, or on trio and other event
    loops through AnyIO (``mediary[anyio]``).
    """

    async def publish(self, calls: Sequence[NotificationCall], /) -> None:
        """Run the handlers as tasks and wait for all of them."""
        failures = [error for error in await run_all(calls) if error is not None]
        if failures:
            raise ExceptionGroup(f"{len(failures)} notification handler(s) failed", failures)
