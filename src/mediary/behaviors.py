"""Ready-made behaviors: logging, retry and timeout.

They are never scanned; add the ones you want, configured, with `Mediator.use`:

```python
mediator.use(LoggingBehavior(), order=-100)
mediator.use(TimeoutBehavior(seconds=5), order=-50)
mediator.use(RetryBehavior(max_retries=3), kinds={"request"})
```

They wrap every message they are added for, so narrow them with `kinds=` where it matters:
retrying is only safe for handlers that can run twice.
"""

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from ._behaviors import Next
from ._errors import HandlerTimeout
from ._markers import marker_of
from ._retryable import is_retryable

__all__ = ["LoggingBehavior", "RetryBehavior", "TimeoutBehavior"]

_T = TypeVar("_T")


def _qualified_name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


class LoggingBehavior:
    """Log each message's start, completion (or slowness) and failure, with its duration.

    Records carry structured `extra` fields: `mediary_kind` (the decorator kind, such as
    "request" or "notification"), `mediary_type` (the message's qualified class name),
    `mediary_payload` (its repr, truncated) and, once finished, `mediary_duration_ms`.

    Levels: start is DEBUG, completion `level` (INFO), completion slower than `slow_after`
    seconds WARNING, and failure ERROR with the traceback. `clock` returns seconds; inject one
    to test timing.
    """

    def __init__(
        self,
        logger: logging.Logger | None = None,
        *,
        level: int = logging.INFO,
        slow_after: float | None = 1.0,
        max_payload: int = 200,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        """Configure where and how messages are logged."""
        self.logger = logger if logger is not None else logging.getLogger("mediary")
        self.level = level
        self.slow_after = slow_after
        self.max_payload = max_payload
        self.clock = clock

    async def handle(self, message: object, next: Next[_T]) -> _T:
        """Log around the rest of the pipeline."""
        message_type = type(message)
        marker = marker_of(message_type)
        kind = marker.kind if marker is not None else "message"
        name = _qualified_name(message_type)
        extra: dict[str, Any] = {
            "mediary_kind": kind,
            "mediary_type": name,
            "mediary_payload": self._summary(message),
        }
        self.logger.debug("%s %s started", kind, name, extra=extra)
        started = self.clock()
        try:
            result = await next()
        except Exception:
            extra["mediary_duration_ms"] = self._elapsed_ms(started)
            self.logger.exception(
                "%s %s failed after %.1fms", kind, name, extra["mediary_duration_ms"], extra=extra
            )
            raise
        duration_ms = extra["mediary_duration_ms"] = self._elapsed_ms(started)
        if self.slow_after is not None and duration_ms >= self.slow_after * 1000:
            self.logger.warning("%s %s was slow: %.1fms", kind, name, duration_ms, extra=extra)
        else:
            self.logger.log(
                self.level, "%s %s completed in %.1fms", kind, name, duration_ms, extra=extra
            )
        return result

    def _elapsed_ms(self, started: float) -> float:
        return (self.clock() - started) * 1000

    def _summary(self, message: object) -> str:
        text = repr(message)
        if len(text) <= self.max_payload:
            return text
        return text[: self.max_payload] + "…"


class RetryBehavior:
    """Run the rest of the pipeline again when it fails with a transient error.

    An error is transient when its class is marked `@retryable` (as `TransientError` and its
    subclasses are) or is one of `retry_on`, which is for errors that can't be marked, such as
    `ConnectionError`. Any other error fails at once.

    After the first attempt it retries up to `max_retries` times, sleeping an exponentially
    growing delay between attempts: `base_delay * 2**n`, capped at `max_delay`, and with
    `jitter` a random fraction of that (full jitter), so that callers don't retry in lockstep.
    The last error propagates. Inject `sleep` and `random` to test without waiting.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_on: tuple[type[Exception], ...] = (),
        base_delay: float = 0.1,
        max_delay: float = 10.0,
        jitter: bool = True,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
        random: Callable[[], float] = random.random,
    ) -> None:
        """Configure what is retried, how often and how long to wait.

        Raises:
            ValueError: a count or delay is negative.

        """
        if max_retries < 0 or base_delay < 0 or max_delay < 0:
            raise ValueError("max_retries, base_delay and max_delay must not be negative")
        self.max_retries = max_retries
        self.retry_on = retry_on
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.sleep = sleep
        self.random = random

    async def handle(self, message: object, next: Next[_T]) -> _T:
        """Call `next()` until it succeeds or the retries run out."""
        for retry in range(self.max_retries):
            try:
                return await next()
            except Exception as error:
                if not self.retries(error):
                    raise
            await self.sleep(self.delay(retry))
        return await next()

    def retries(self, error: Exception) -> bool:
        """Whether `error` is transient: marked `@retryable`, or one of `retry_on`."""
        return is_retryable(error) or isinstance(error, self.retry_on)

    def delay(self, retry: int) -> float:
        """Return the seconds to wait before retry number `retry` (counting from 0)."""
        delay = min(self.max_delay, self.base_delay * 2**retry)
        return delay * self.random() if self.jitter else delay


class TimeoutBehavior:
    """Fail with `HandlerTimeout` when the rest of the pipeline takes longer than `seconds`.

    The downstream work is cancelled. A `TimeoutError` raised by the handler itself passes
    through unchanged.
    """

    def __init__(self, seconds: float) -> None:
        """Set the time limit.

        Raises:
            ValueError: `seconds` isn't positive.

        """
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self.seconds = seconds

    async def handle(self, message: object, next: Next[_T]) -> _T:
        """Await `next()` within the time limit."""
        deadline = asyncio.timeout(self.seconds)
        try:
            async with deadline:
                return await next()
        except TimeoutError as exc:
            if deadline.expired():
                raise HandlerTimeout(type(message), self.seconds) from exc
            raise
