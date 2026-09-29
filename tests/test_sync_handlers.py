"""Sync handlers: plain `def` handlers, run on a worker thread under asyncio and trio."""

import contextvars
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field

import anyio
import pytest
from conftest import MakePackage

from mediary import (
    Concurrent,
    HandlerTimeout,
    InvalidBehavior,
    InvalidHandler,
    Mediator,
    Next,
    Returns,
    Yields,
    handler,
    notification,
    request,
    stream_request,
)
from mediary.behaviors import TimeoutBehavior


@request
@dataclass(frozen=True)
class Greet(Returns[str]):
    name: str


@notification
@dataclass(frozen=True)
class Greeted:
    name: str


@stream_request
class Count(Yields[int]):
    pass


@dataclass
class Greeter:
    greeting: str = "hello"


def greet(request: Greet, greeter: Greeter) -> str:
    return f"{greeter.greeting} {request.name} from {threading.current_thread().name}"


class GreetHandler:
    def handle(self, request: Greet) -> str:
        return f"hi {request.name}"


@dataclass
class Log:
    entries: list[str] = field(default_factory=list[str])
    threads: set[int] = field(default_factory=set[int])


async def test_a_sync_function_handler_runs_on_a_worker_thread() -> None:
    m = Mediator()
    m.register(Greet, greet)
    result = await m.send(Greet("ada"))
    assert result.startswith("hello ada from ")
    assert not result.endswith(threading.main_thread().name)


async def test_a_sync_class_handler_is_sent_to() -> None:
    m = Mediator()
    m.register(Greet, GreetHandler)
    assert await m.send(Greet("ada")) == "hi ada"


async def test_a_sync_singleton_is_resolved_once() -> None:
    @handler(lifetime="singleton")
    class Counter:
        def __init__(self) -> None:
            self.calls = 0

        def handle(self, request: Greet) -> str:
            self.calls += 1
            return str(self.calls)

    m = Mediator()
    m.register(Greet, Counter)
    assert [await m.send(Greet("ada")) for _ in range(3)] == ["1", "2", "3"]


async def test_sync_notification_handlers_are_published_to_on_threads() -> None:
    log = Log()

    def first(event: Greeted) -> None:
        log.entries.append(f"first {event.name}")
        log.threads.add(threading.get_ident())

    class Second:
        def handle(self, event: Greeted) -> None:
            log.entries.append(f"second {event.name}")
            log.threads.add(threading.get_ident())

    m = Mediator()
    m.register(Greeted, first)
    m.register(Greeted, Second)
    await m.publish(Greeted("ada"))
    await m.publish(Greeted("bob"), strategy=Concurrent())
    assert sorted(log.entries) == ["first ada", "first bob", "second ada", "second bob"]
    assert threading.get_ident() not in log.threads


async def test_sync_handlers_are_scanned(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "handlers.py": """
                from mediary import Returns, handler, notification, request

                @request
                class Ping(Returns[str]):
                    pass

                @notification
                class Pinged:
                    pass

                @handler
                def ping(request: Ping) -> str:
                    return "pong"

                @handler
                class PingedHandler:
                    def handle(self, event: Pinged) -> None:
                        pass
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    module = __import__(f"{pkg}.handlers", fromlist=["Ping"])
    assert await m.send(module.Ping()) == "pong"
    await m.publish(module.Pinged())


async def test_the_event_loop_keeps_running_while_a_sync_handler_blocks() -> None:
    released = threading.Event()

    def blocking(request: Greet) -> str:
        # Only a task on the event loop sets the event, so this returns in time only if the
        # event loop kept running while it blocked.
        return "released" if released.wait(timeout=5) else "starved"

    async def release() -> None:
        await anyio.sleep(0.01)
        released.set()

    m = Mediator()
    m.register(Greet, blocking)
    results: list[str] = []

    async def send() -> None:
        results.append(await m.send(Greet("ada")))

    async with anyio.create_task_group() as group:
        group.start_soon(send)
        group.start_soon(release)
    assert results == ["released"]


async def test_behaviors_wrap_sync_handlers() -> None:
    log: list[str] = []

    async def around(request: Greet, next: Next[str]) -> str:
        log.append("before")
        result = await next()
        log.append(f"after {result}")
        return result

    m = Mediator()
    m.register(Greet, GreetHandler)
    m.use(around)
    assert await m.send(Greet("ada")) == "hi ada"
    assert log == ["before", "after hi ada"]


async def test_a_timeout_does_not_wait_for_a_blocked_sync_handler() -> None:
    released = threading.Event()

    def stuck(request: Greet) -> str:
        released.wait(timeout=5)
        return "late"

    m = Mediator()
    m.register(Greet, stuck)
    m.use(TimeoutBehavior(0.05))
    try:
        with anyio.fail_after(2), pytest.raises(HandlerTimeout):
            await m.send(Greet("ada"))
    finally:
        released.set()  # let the abandoned thread finish


async def test_context_variables_reach_the_worker_thread() -> None:
    user: contextvars.ContextVar[str] = contextvars.ContextVar("user")

    def whoami(request: Greet) -> str:
        return user.get()

    m = Mediator()
    m.register(Greet, whoami)
    user.set("ada")
    assert await m.send(Greet("")) == "ada"


def test_a_sync_generator_is_not_a_stream_handler() -> None:
    def count(request: Count) -> Iterator[int]:
        yield 1

    class CountHandler:
        def handle(self, request: Count) -> Iterator[int]:
            yield 1

    for source in (count, CountHandler):
        with pytest.raises(InvalidHandler, match="must be async generators"):
            Mediator().register(Count, source)


def test_a_sync_function_is_not_a_stream_handler() -> None:
    def count(request: Count) -> list[int]:
        return [1]

    with pytest.raises(InvalidHandler, match="are async generators"):
        Mediator().register(Count, count)


def test_behaviors_must_be_async() -> None:
    def sync_behavior(request: Greet, next: Next[str]) -> str:
        return "never"

    class SyncBehavior:
        def handle(self, request: Greet, next: Next[str]) -> str:
            return "never"

    for behavior in (sync_behavior, SyncBehavior, SyncBehavior()):
        with pytest.raises(InvalidBehavior, match="it is sync, but must be async"):
            Mediator().use(behavior)  # pyright: ignore[reportArgumentType]
