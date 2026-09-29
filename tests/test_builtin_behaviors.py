import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

import anyio
import pytest

from mediary import (
    HandlerTimeout,
    Mediator,
    Returns,
    TransientError,
    Yields,
    notification,
    request,
    retryable,
    stream_request,
)
from mediary.behaviors import LoggingBehavior, RetryBehavior, TimeoutBehavior


@request
@dataclass(frozen=True)
class Work(Returns[str]):
    payload: str = "x"


@notification
@dataclass(frozen=True)
class Happened:
    pass


@stream_request
@dataclass(frozen=True)
class Numbers(Yields[int]):
    count: int
    fail_after: int | None = None


async def numbers(request: Numbers) -> AsyncIterator[int]:
    for n in range(request.count):
        if n == request.fail_after:
            raise ValueError("bad")
        yield n


class Script:
    """A handler whose outcome each test scripts: errors to raise first, then a result."""

    errors: ClassVar[list[BaseException]] = []
    delay = 0.0
    calls = 0

    async def handle(self, request: Work) -> str:
        Script.calls += 1
        if Script.delay:
            await anyio.sleep(Script.delay)
        if Script.errors:
            raise Script.errors.pop(0)
        return "done"


@pytest.fixture(autouse=True)
def reset_script() -> None:
    Script.errors, Script.delay, Script.calls = [], 0.0, 0


def mediator_with(*behaviors: Any) -> Mediator:
    m = Mediator()
    m.register(Work, Script)
    for b in behaviors:
        m.use(b)
    return m


class Clock:
    def __init__(self, *ticks: float) -> None:
        self.ticks = list(ticks)

    def __call__(self) -> float:
        return self.ticks.pop(0)


# Logging


@pytest.fixture
def logs(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG, logger="test.mediary")
    return caplog


def logging_behavior(*ticks: float, **options: Any) -> LoggingBehavior:
    return LoggingBehavior(logging.getLogger("test.mediary"), clock=Clock(*ticks), **options)


async def test_logging_records_start_and_completion(logs: pytest.LogCaptureFixture) -> None:
    assert await mediator_with(logging_behavior(10.0, 10.25)).send(Work()) == "done"

    start, done = logs.records
    assert (start.levelno, start.getMessage()) == (
        logging.DEBUG,
        "request test_builtin_behaviors.Work started",
    )
    assert (done.levelno, done.getMessage()) == (
        logging.INFO,
        "request test_builtin_behaviors.Work completed in 250.0ms",
    )
    assert done.__dict__["mediary_kind"] == "request"
    assert done.__dict__["mediary_type"] == "test_builtin_behaviors.Work"
    assert done.__dict__["mediary_payload"] == "Work(payload='x')"
    assert done.__dict__["mediary_duration_ms"] == 250.0


async def test_logging_warns_about_slow_messages(logs: pytest.LogCaptureFixture) -> None:
    await mediator_with(logging_behavior(0.0, 2.0, slow_after=1.5)).send(Work())
    assert logs.records[-1].levelno == logging.WARNING
    assert logs.records[-1].getMessage().endswith("was slow: 2000.0ms")


async def test_logging_can_skip_slowness_and_use_its_own_level(
    logs: pytest.LogCaptureFixture,
) -> None:
    await mediator_with(logging_behavior(0.0, 99.0, slow_after=None, level=logging.DEBUG)).send(
        Work()
    )
    assert logs.records[-1].levelno == logging.DEBUG
    assert "completed" in logs.records[-1].getMessage()


async def test_logging_records_failures_and_reraises(logs: pytest.LogCaptureFixture) -> None:
    Script.errors = [ValueError("bad")]
    with pytest.raises(ValueError, match="bad"):
        await mediator_with(logging_behavior(1.0, 1.5)).send(Work())
    failed = logs.records[-1]
    assert failed.levelno == logging.ERROR
    assert failed.getMessage() == "request test_builtin_behaviors.Work failed after 500.0ms"
    assert failed.exc_info is not None


async def test_logging_classifies_by_decorator_kind_and_truncates_payloads(
    logs: pytest.LogCaptureFixture,
) -> None:
    m = mediator_with(logging_behavior(0.0, 0.0, 0.0, 0.0, max_payload=10))
    await m.publish(Happened())
    await m.send(Work("y" * 50))
    kinds = [r.__dict__["mediary_kind"] for r in logs.records]
    assert kinds == ["notification", "notification", "request", "request"]
    assert logs.records[-1].__dict__["mediary_payload"] == "Work(paylo…"


async def test_logging_labels_undecorated_messages() -> None:
    seen: list[str] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            seen.append(record.__dict__["mediary_kind"])

    logger = logging.getLogger("test.mediary.capture")
    logger.addHandler(Capture())
    logger.setLevel(logging.INFO)

    async def next() -> str:
        return "ok"

    await LoggingBehavior(logger, clock=Clock(0.0, 0.0)).handle(object(), next)
    assert seen == ["message"]


def streaming(*ticks: float, **options: Any) -> Mediator:
    m = Mediator()
    m.register(Numbers, numbers)
    m.use(logging_behavior(*ticks, **options))
    return m


async def test_logging_records_a_stream_until_it_ends(logs: pytest.LogCaptureFixture) -> None:
    async with streaming(1.0, 1.5).stream(Numbers(3)) as items:
        assert [n async for n in items] == [0, 1, 2]
    start, done = logs.records
    assert start.getMessage() == "stream_request test_builtin_behaviors.Numbers started"
    assert (done.levelno, done.getMessage()) == (
        logging.INFO,
        "stream_request test_builtin_behaviors.Numbers completed in 500.0ms",
    )
    assert done.__dict__["mediary_items"] == 3


async def test_logging_records_a_stream_closed_early(logs: pytest.LogCaptureFixture) -> None:
    async with streaming(0.0, 0.1).stream(Numbers(10)) as items:
        async for n in items:
            if n == 1:
                break
    done = logs.records[-1]
    assert (
        done.getMessage() == "stream_request test_builtin_behaviors.Numbers closed early in 100.0ms"
    )
    assert done.__dict__["mediary_items"] == 2


async def test_logging_records_a_failed_stream(logs: pytest.LogCaptureFixture) -> None:
    received: list[int] = []

    async def consume() -> None:
        async with streaming(0.0, 2.0, slow_after=1.0).stream(Numbers(5, fail_after=2)) as items:
            async for n in items:
                received.append(n)  # noqa: PERF401 - keeps the items before the error

    with pytest.raises(ValueError, match="bad"):
        await consume()
    assert received == [0, 1]
    failed = logs.records[-1]
    assert failed.levelno == logging.ERROR
    assert failed.getMessage().endswith("failed after 2000.0ms")
    assert failed.__dict__["mediary_items"] == 2


def test_logging_defaults_to_the_mediary_logger() -> None:
    assert LoggingBehavior().logger is logging.getLogger("mediary")


# Retry


class Sleeps:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


class Unavailable(TransientError):
    pass


@retryable
class StorageError(Exception):
    pass


class DiskFull(StorageError):
    pass


async def test_retry_backs_off_exponentially_with_jitter() -> None:
    Script.errors = [Unavailable(), Unavailable()]
    sleep = Sleeps()
    retry = RetryBehavior(sleep=sleep, random=lambda: 0.5)
    assert await mediator_with(retry).send(Work()) == "done"
    assert Script.calls == 3
    assert sleep.delays == [0.05, 0.1]


async def test_retry_delays_are_capped() -> None:
    retry = RetryBehavior(base_delay=1, max_delay=3, jitter=False)
    assert [retry.delay(n) for n in range(4)] == [1, 2, 3, 3]


async def test_retry_gives_up_with_the_last_error() -> None:
    Script.errors = [Unavailable("1"), Unavailable("2"), Unavailable("3")]
    sleep = Sleeps()
    with pytest.raises(Unavailable, match="3"):
        await mediator_with(RetryBehavior(max_retries=2, sleep=sleep, jitter=False)).send(Work())
    assert Script.calls == 3
    assert sleep.delays == [0.1, 0.2]


@pytest.mark.parametrize(
    ("error", "retried"),
    [
        (Unavailable(), True),
        (StorageError(), True),
        (DiskFull(), True),
        (ValueError(), False),
        (ConnectionError(), False),
        (TimeoutError(), False),
    ],
)
def test_retry_only_retries_errors_marked_retryable(error: Exception, retried: bool) -> None:
    assert RetryBehavior().retries(error) is retried


def test_retry_on_adds_errors_that_cannot_be_marked() -> None:
    retry = RetryBehavior(retry_on=(ConnectionError,))
    assert retry.retries(ConnectionResetError())
    assert retry.retries(Unavailable())
    assert not retry.retries(TimeoutError())


async def test_errors_that_are_not_transient_fail_at_once() -> None:
    Script.errors = [ValueError("not transient")]
    sleep = Sleeps()
    with pytest.raises(ValueError, match="not transient"):
        await mediator_with(RetryBehavior(sleep=sleep)).send(Work())
    assert (Script.calls, sleep.delays) == (1, [])


async def test_retry_can_be_disabled() -> None:
    Script.errors = [Unavailable()]
    with pytest.raises(Unavailable):
        await mediator_with(RetryBehavior(max_retries=0)).send(Work())
    assert Script.calls == 1


def test_marking_a_subclass_leaves_its_base_alone() -> None:
    @retryable
    class Flaky(ValueError):
        pass

    assert RetryBehavior().retries(Flaky())
    assert not RetryBehavior().retries(ValueError())


@pytest.mark.parametrize(
    ("target", "reason"),
    [
        (object, "decorates exception classes"),
        (KeyboardInterrupt, "decorates exception classes"),
        (ConnectionError, r"retry_on=\(ConnectionError,\)"),
    ],
)
def test_retryable_needs_an_exception_class_it_can_mark(target: Any, reason: str) -> None:
    with pytest.raises(TypeError, match=reason):
        retryable(target)


@pytest.mark.parametrize(
    "settings", [{"max_retries": -1}, {"base_delay": -1.0}, {"max_delay": -1.0}]
)
def test_retry_rejects_negative_settings(settings: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        RetryBehavior(**settings)  # pyright: ignore[reportArgumentType]


# Timeout


async def test_timeout_fails_slow_messages_with_a_clear_error() -> None:
    Script.delay = 10
    with pytest.raises(HandlerTimeout) as exc:
        await mediator_with(TimeoutBehavior(0.01)).send(Work())
    assert isinstance(exc.value, TimeoutError)
    assert exc.value.message_type is Work
    assert exc.value.seconds == 0.01
    assert str(exc.value) == "test_builtin_behaviors.Work was not handled within 0.01s"


async def test_timeout_lets_fast_messages_and_their_own_timeouts_through() -> None:
    m = mediator_with(TimeoutBehavior(5))
    assert await m.send(Work()) == "done"
    Script.errors = [TimeoutError("upstream")]
    with pytest.raises(TimeoutError, match="upstream") as exc:
        await m.send(Work())
    assert not isinstance(exc.value, HandlerTimeout)


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        TimeoutBehavior(0)


# Wiring


async def test_built_ins_compose_as_configured_instances(logs: pytest.LogCaptureFixture) -> None:
    Script.errors = [Unavailable()]
    m = mediator_with()
    m.use(logging_behavior(0.0, 0.0), order=0)
    m.use(TimeoutBehavior(5), order=1)
    m.use(RetryBehavior(sleep=Sleeps()), order=2)
    assert await m.send(Work()) == "done"
    assert [r.levelno for r in logs.records] == [logging.DEBUG, logging.INFO]


async def test_built_ins_are_never_scanned() -> None:
    m = mediator_with()
    m.scan("mediary.behaviors")
    Script.errors = [Unavailable()]
    with pytest.raises(Unavailable):
        await m.send(Work())
