import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, TypeVar

import pytest
from conftest import MakePackage

from mediary import (
    HandlerNotFound,
    InvalidHandlerSignature,
    Mediator,
    Next,
    NextStream,
    Returns,
    RuleViolation,
    Stream,
    Yields,
    behavior,
    handler,
    notification,
    request,
    stream_request,
)
from mediary.kinds import HandlerInfo, define_kind

T = TypeVar("T")


@stream_request
@dataclass(frozen=True)
class Count(Yields[int]):
    up_to: int


@request
@dataclass(frozen=True)
class Ping(Returns[str]):
    pass


@notification
class Happened:
    pass


@dataclass
class Log:
    """Records what the handlers and behaviors of a test did, in order."""

    lines: list[str] = field(default_factory=list[str])


async def count(request: Count, log: Log) -> AsyncIterator[int]:
    log.lines.append("count started")
    try:
        for n in range(request.up_to):
            yield n
    finally:
        log.lines.append("count closed")


async def ping(request: Ping) -> str:
    return "pong"


class SharedLog:
    """Resolves one `Log` for every dependency, so a test can read what happened."""

    def __init__(self) -> None:
        self.log = Log()

    def resolve(self, cls: type[T]) -> T:
        return self.log if cls is Log else cls()  # pyright: ignore[reportReturnType]


def mediator_with(*behaviors: Any) -> tuple[Mediator, list[str]]:
    resolver = SharedLog()
    m = Mediator(resolver=resolver)
    m.register(Count, count)
    m.register(Ping, ping)
    for b in behaviors:
        m.use(b)
    return m, resolver.log.lines


async def items(stream: Stream[T]) -> list[T]:
    return [item async for item in stream]


# Handlers


async def test_a_stream_yields_its_handlers_items() -> None:
    m, _ = mediator_with()
    assert await items(m.stream(Count(3))) == [0, 1, 2]


async def test_nothing_runs_until_the_stream_is_iterated() -> None:
    m, log = mediator_with()
    stream = m.stream(Count(3))
    assert log == []
    assert await anext(stream) == 0
    assert log == ["count started"]


async def test_items_are_produced_as_they_are_asked_for() -> None:
    produced: list[int] = []

    @stream_request
    class Naturals(Yields[int]):
        pass

    async def naturals(request: Naturals) -> AsyncIterator[int]:
        n = 0
        while True:
            produced.append(n)
            yield n
            n += 1

    m = Mediator()
    m.register(Naturals, naturals)
    async with m.stream(Naturals()) as stream:
        assert [await anext(stream) for _ in range(3)] == [0, 1, 2]
    assert produced == [0, 1, 2]


async def test_class_handlers_stream_and_can_be_singletons() -> None:
    @handler(lifetime="singleton")
    class Counter:
        def __init__(self) -> None:
            self.streams = 0

        async def handle(self, request: Count) -> AsyncIterator[int]:
            self.streams += 1
            for _ in range(request.up_to):
                yield self.streams

    m = Mediator()
    m.register(Count, Counter)
    assert await items(m.stream(Count(2))) == [1, 1]
    assert await items(m.stream(Count(2))) == [2, 2]


async def test_a_stream_is_its_own_iterator() -> None:
    m, _ = mediator_with()
    stream = m.stream(Count(3))
    assert aiter(stream) is stream
    assert await anext(stream) == 0
    assert await items(stream) == [1, 2]


async def test_handler_errors_reach_the_consumer() -> None:
    @stream_request
    class Broken(Yields[int]):
        pass

    async def broken(request: Broken) -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("halfway")

    m = Mediator()
    m.register(Broken, broken)
    stream = m.stream(Broken())
    assert await anext(stream) == 1
    with pytest.raises(RuntimeError, match="halfway"):
        await anext(stream)


# Dispatch


async def test_streaming_needs_a_handler_and_says_so_at_once() -> None:
    m, _ = mediator_with()

    @stream_request
    class Unhandled:
        pass

    with pytest.raises(HandlerNotFound):
        m.stream(Unhandled())
    with pytest.raises(HandlerNotFound):
        m.stream(Ping())


async def test_stream_requests_cannot_be_sent() -> None:
    m, _ = mediator_with()
    with pytest.raises(HandlerNotFound):
        await m.send(Count(1))


async def _returns(request: Count) -> int:
    return 1


async def _yields_for_request(request: Ping) -> AsyncIterator[str]:
    yield "pong"


async def _yields_for_notification(event: Happened) -> AsyncIterator[None]:
    yield None


@pytest.mark.parametrize(
    ("message", "function", "reason"),
    [
        (Count, _returns, "@stream_request handlers are async generators"),
        (Ping, _yields_for_request, "@request handlers `return` a result"),
        (Happened, _yields_for_notification, "@notification handlers `return` a result"),
    ],
)
def test_only_stream_requests_have_async_generator_handlers(
    message: type, function: Any, reason: str
) -> None:
    with pytest.raises(InvalidHandlerSignature, match=reason):
        Mediator().register(message, function)


async def test_custom_kinds_can_stream_and_have_rules() -> None:
    def typed(info: HandlerInfo) -> str | None:
        return None if info.returns is not Any else "hint what it yields"

    feed = define_kind("feed", dispatch="stream", rules=[typed])

    @feed
    class Prices(Yields[float]):
        pass

    async def prices(request: Prices) -> AsyncIterator[float]:
        yield 1.5

    async def untyped(request: Prices) -> Any:
        yield 1.5

    m = Mediator()
    m.register(Prices, prices)
    assert await items(m.stream(Prices())) == [1.5]
    with pytest.raises(RuleViolation, match="hint what it yields"):
        Mediator().register(Prices, untyped)


async def test_scan_finds_stream_handlers_and_behaviors(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "feed.py": """
                from collections.abc import AsyncIterator
                from mediary import NextStream, Yields, behavior, handler, stream_request

                @stream_request
                class Letters(Yields[str]):
                    pass

                @handler
                class LettersHandler:
                    async def handle(self, request: Letters) -> AsyncIterator[str]:
                        for letter in "ab":
                            yield letter

                @behavior
                async def shout(request: Letters, next: NextStream[str]) -> AsyncIterator[str]:
                    async for letter in next():
                        yield letter.upper()
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    feed: Any = __import__(f"{pkg}.feed").feed
    assert await items(m.stream(feed.Letters())) == ["A", "B"]


# Behaviors


async def test_stream_behaviors_wrap_streams_in_order() -> None:
    @behavior(order=1)
    async def double(request: Count, next: NextStream[int]) -> AsyncIterator[int]:
        async for n in next():
            yield n * 2

    @behavior(order=0)
    async def evens_only(request: object, next: NextStream[int]) -> AsyncIterator[int]:
        async for n in next():
            if n % 4 == 0:
                yield n

    m, _ = mediator_with(double, evens_only)
    assert await items(m.stream(Count(5))) == [0, 4, 8]


async def test_streams_and_sends_each_get_only_their_own_behaviors() -> None:
    wrapped: list[str] = []

    async def around_sends(request: object, next: Next[Any]) -> Any:
        wrapped.append(f"send {type(request).__name__}")
        return await next()

    async def around_streams(request: object, next: NextStream[Any]) -> AsyncIterator[Any]:
        wrapped.append(f"stream {type(request).__name__}")
        async for item in next():
            yield item

    m, _ = mediator_with(around_sends, around_streams)
    assert await m.send(Ping()) == "pong"
    assert await items(m.stream(Count(1))) == [0]
    assert wrapped == ["send Ping", "stream Count"]


async def test_stream_behaviors_can_target_kinds() -> None:
    @behavior(kinds={"feed_only"})
    async def never(request: object, next: NextStream[Any]) -> AsyncIterator[Any]:
        yield "wrong"

    m, _ = mediator_with(never)
    assert await items(m.stream(Count(1))) == [0]


async def test_stream_behaviors_can_be_classes_instances_and_take_dependencies() -> None:
    class Offset:
        def __init__(self, by: int = 10) -> None:
            self.by = by

        async def handle(self, request: Count, next: NextStream[int]) -> AsyncIterator[int]:
            async for n in next():
                yield n + self.by

    async def logged(request: Count, next: NextStream[int], log: Log) -> AsyncIterator[int]:
        async for n in next():
            log.lines.append(f"item {n}")
            yield n

    m, log = mediator_with(Offset)
    m.use(Offset(100), order=1)
    m.use(logged, order=2)
    assert await items(m.stream(Count(2))) == [110, 111]
    assert log == ["count started", "item 0", "item 1", "count closed"]


async def test_a_stream_behavior_can_answer_without_the_handler() -> None:
    async def cached(request: Count, next: NextStream[int]) -> AsyncIterator[int]:
        for n in (7, 8):
            yield n

    m, log = mediator_with(cached)
    assert await items(m.stream(Count(3))) == [7, 8]
    assert log == []


async def test_a_stream_behavior_can_reopen_the_rest_of_the_pipeline() -> None:
    attempts: list[int] = []

    @stream_request
    class Flaky(Yields[str]):
        pass

    async def flaky(request: Flaky) -> AsyncIterator[str]:
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise ConnectionError
        yield "ok"

    async def retry(request: Flaky, next: NextStream[str]) -> AsyncIterator[str]:
        try:
            first = await anext(next())
        except ConnectionError:
            first = await anext(next())
        yield first

    m = Mediator()
    m.register(Flaky, flaky)
    m.use(retry)
    assert await items(m.stream(Flaky())) == ["ok"]
    assert attempts == [0, 1]


async def test_stream_behaviors_can_handle_handler_errors() -> None:
    @stream_request
    class Broken(Yields[int]):
        pass

    async def broken(request: Broken) -> AsyncIterator[int]:
        yield 1
        raise RuntimeError("boom")

    async def recover(request: Broken, next: NextStream[int]) -> AsyncIterator[int]:
        try:
            async for n in next():
                yield n
        except RuntimeError:
            yield -1

    m = Mediator()
    m.register(Broken, broken)
    m.use(recover)
    assert await items(m.stream(Broken())) == [1, -1]


# Closing and cancellation


def closing(name: str, log: list[str]) -> Any:
    """A stream behavior that logs when it is closed, and never closes `next()` itself."""

    async def close_logged(request: Count, next: NextStream[int]) -> AsyncIterator[int]:
        try:
            async for n in next():
                yield n
        finally:
            log.append(f"{name} closed")

    close_logged.__qualname__ = name
    return close_logged


async def test_leaving_async_with_closes_the_whole_pipeline_at_once() -> None:
    m, log = mediator_with()
    m.use(closing("outer", log), order=0)
    m.use(closing("inner", log), order=1)
    async with m.stream(Count(100)) as stream:
        async for n in stream:
            if n == 2:
                break
        assert log == ["count started"]
    assert log == ["count started", "outer closed", "inner closed", "count closed"]


async def test_aclose_closes_the_pipeline_and_can_be_repeated() -> None:
    log: list[str] = []
    m, _ = mediator_with(closing("behavior", log))
    stream = m.stream(Count(100))
    await anext(stream)
    await stream.aclose()
    await stream.aclose()
    assert log == ["behavior closed"]
    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_an_error_in_the_block_closes_the_stream_and_propagates() -> None:
    m, log = mediator_with()

    async def consume() -> None:
        async with m.stream(Count(100)) as stream:
            await anext(stream)
            raise ValueError("consumer")

    with pytest.raises(ValueError, match="consumer"):
        await consume()
    assert log == ["count started", "count closed"]


async def test_a_stream_closed_before_it_starts_never_runs_its_handler() -> None:
    m, log = mediator_with()
    async with m.stream(Count(3)):
        pass
    assert log == []


async def test_cancelling_the_consumer_reaches_the_handler() -> None:
    @stream_request
    class Ticks(Yields[int]):
        pass

    started = asyncio.Event()
    cleaned: list[str] = []

    async def ticks(request: Ticks) -> AsyncIterator[int]:
        try:
            yield 0
            started.set()
            await asyncio.Event().wait()
            yield 1
        finally:
            cleaned.append("ticks")

    m = Mediator()
    m.register(Ticks, ticks)

    async def consume() -> None:
        async with m.stream(Ticks()) as stream:
            async for _ in stream:
                pass

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned == ["ticks"]
