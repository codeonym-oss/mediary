from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import anyio
import pytest
from conftest import MakePackage

from mediary import (
    Concurrent,
    HandlerNotFound,
    Mediator,
    Next,
    NotAMessage,
    NotANotification,
    Sequential,
    handler,
    notification,
    request,
)


@notification
@dataclass(frozen=True)
class UserRegistered:
    user_id: int


@request
class Ping:
    pass


async def ping(request: Ping) -> str:
    return "pong"


def recording(log: list[str], *names: str, fail: set[str] | None = None) -> list[Any]:
    """Build function handlers named `names` that append their name to `log`."""

    def make(name: str) -> Any:
        async def handle(event: UserRegistered) -> None:
            log.append(name)
            if fail and name in fail:
                raise RuntimeError(name)

        handle.__qualname__ = name
        return handle

    return [make(name) for name in names]


def subscribed(*handlers: Any, **options: Any) -> Mediator:
    m = Mediator(**options)
    m.register(Ping, ping)
    for h in handlers:
        m.register(UserRegistered, h)
    return m


async def test_publishing_without_handlers_does_nothing() -> None:
    await Mediator().publish(UserRegistered(1))


async def test_every_handler_runs_in_name_order() -> None:
    log: list[str] = []

    @handler
    class Welcome:
        async def handle(self, event: UserRegistered) -> None:
            log.append("welcome")

    m = subscribed(*recording(log, "c_audit", "a_email"), Welcome)
    await m.publish(UserRegistered(1))
    assert log == ["a_email", "c_audit", "welcome"]


async def test_registering_the_same_handler_twice_runs_it_once() -> None:
    log: list[str] = []
    (only,) = recording(log, "only")
    m = subscribed(only, only)
    await m.publish(UserRegistered(1))
    assert log == ["only"]


async def test_sequential_stops_at_the_first_error() -> None:
    log: list[str] = []
    m = subscribed(*recording(log, "a", "b", "c", fail={"b"}))
    with pytest.raises(RuntimeError, match="b"):
        await m.publish(UserRegistered(1))
    assert log == ["a", "b"]


async def test_concurrent_runs_every_handler_and_groups_failures() -> None:
    log: list[str] = []
    m = subscribed(*recording(log, "a", "b", "c", "d", fail={"d", "b"}))
    with pytest.raises(ExceptionGroup) as exc:
        await m.publish(UserRegistered(1), strategy=Concurrent())
    assert sorted(log) == ["a", "b", "c", "d"]
    assert [str(e) for e in exc.value.exceptions] == ["b", "d"]


async def test_concurrent_handlers_overlap() -> None:
    # Each handler waits for the other to start: run one after the other, in either order,
    # they would never finish.
    first, second = anyio.Event(), anyio.Event()

    async def waits_for_second(event: UserRegistered) -> None:
        first.set()
        await second.wait()

    async def waits_for_first(event: UserRegistered) -> None:
        second.set()
        await first.wait()

    m = subscribed(waits_for_second, waits_for_first, publish_strategy=Concurrent())
    with anyio.fail_after(1):
        await m.publish(UserRegistered(1))


@pytest.mark.parametrize("limit", [1, 3])
async def test_concurrent_runs_at_most_limit_handlers_at_once(limit: int) -> None:
    running = peak = 0

    def make(name: str) -> Any:
        async def handle(event: UserRegistered) -> None:
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            await anyio.sleep(0.01)
            running -= 1

        handle.__qualname__ = name
        return handle

    m = subscribed(*(make(f"h{n}") for n in range(8)))
    await m.publish(UserRegistered(1), strategy=Concurrent(limit=limit))
    assert peak == limit


async def test_concurrent_with_a_limit_starts_handlers_in_order() -> None:
    log: list[str] = []
    m = subscribed(*recording(log, "a", "b", "c", "d"))
    await m.publish(UserRegistered(1), strategy=Concurrent(limit=2))
    assert log == ["a", "b", "c", "d"]


async def test_concurrent_with_a_limit_runs_every_handler_and_groups_failures() -> None:
    log: list[str] = []
    m = subscribed(*recording(log, "a", "b", "c", "d", fail={"d", "a"}))
    with pytest.raises(ExceptionGroup) as exc:
        await m.publish(UserRegistered(1), strategy=Concurrent(limit=2))
    assert sorted(log) == ["a", "b", "c", "d"]
    assert [str(e) for e in exc.value.exceptions] == ["a", "d"]


async def test_a_limit_above_the_handler_count_runs_them_all() -> None:
    log: list[str] = []
    m = subscribed(*recording(log, "a", "b"))
    await m.publish(UserRegistered(1), strategy=Concurrent(limit=10))
    assert sorted(log) == ["a", "b"]


@pytest.mark.parametrize("limit", [0, -1])
def test_a_limit_below_one_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        Concurrent(limit=limit)


async def test_the_strategy_is_set_per_mediator_and_per_publish() -> None:
    log: list[str] = []

    class Reversed:
        async def publish(self, handlers: Sequence[Callable[[], Awaitable[Any]]], /) -> None:
            for run in reversed(handlers):
                await run()

    m = subscribed(*recording(log, "a", "b"), publish_strategy=Reversed())
    await m.publish(UserRegistered(1))
    await m.publish(UserRegistered(1), strategy=Sequential())
    assert log == ["b", "a", "a", "b"]


async def test_behaviors_can_target_notifications() -> None:
    log: list[str] = []

    async def around(message: object, next: Next[Any]) -> Any:
        log.append(f"around {type(message).__name__}")
        return await next()

    async def for_notifications(message: object, next: Next[Any]) -> Any:
        log.append("notification only")
        return await next()

    async def for_requests(message: object, next: Next[Any]) -> Any:
        log.append("request only")
        return await next()

    m = subscribed(*recording(log, "handler"))
    m.use(around, order=0)
    m.use(for_notifications, order=1, kinds={"notification"})
    m.use(for_requests, order=1, kinds={"request"})
    await m.publish(UserRegistered(1))
    assert log == ["around UserRegistered", "notification only", "handler"]
    log.clear()
    await m.send(Ping())
    assert log == ["around Ping", "request only"]


async def test_scan_registers_every_notification_handler(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "events.py": """
                from mediary import notification

                @notification
                class Shipped:
                    log: list[str] = []
            """,
            "email.py": """
                from mediary import handler
                from .events import Shipped

                @handler
                async def send_email(event: Shipped) -> None:
                    event.log.append("email")
            """,
            "stock.py": """
                from mediary import handler
                from .events import Shipped

                @handler
                class UpdateStock:
                    async def handle(self, event: Shipped) -> None:
                        event.log.append("stock")
            """,
        }
    )
    m = Mediator()
    m.scan(pkg)
    events: Any = __import__(f"{pkg}.events").events
    await m.publish(events.Shipped())
    assert events.Shipped.log == ["email", "stock"]


async def test_only_notifications_can_be_published() -> None:
    with pytest.raises(NotANotification, match="send it with `send`"):
        await subscribed().publish(Ping())


async def test_notifications_cannot_be_sent() -> None:
    m = subscribed(*recording([], "a"))
    with pytest.raises(HandlerNotFound):
        await m.send(UserRegistered(1))


def test_handlers_need_a_request_or_notification() -> None:
    class Plain:
        pass

    async def handle(message: Plain) -> None: ...

    with pytest.raises(NotAMessage, match="@notification"):
        Mediator().register(Plain, handle)
