import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import pytest
from conftest import MakePackage

from mediary import (
    DuplicateHandler,
    InvalidHandlerSignature,
    Mediator,
    Returns,
    handler,
    request,
)

T = TypeVar("T")


@request
@dataclass(frozen=True)
class Greet(Returns[str]):
    name: str


@dataclass
class Greeter:
    greeting: str = "hello"


@dataclass
class Clock:
    now: str = "noon"


@dataclass
class RecordingResolver:
    """Builds `Greeter`s with a custom greeting and records every type it resolves."""

    greeting: str = "hi"
    resolved: list[type] = field(default_factory=list[type])

    def resolve(self, cls: type[T]) -> T:
        self.resolved.append(cls)
        if cls is Greeter:
            return Greeter(self.greeting)  # pyright: ignore[reportReturnType]
        if cls is GreetHandler:
            return GreetHandler(Greeter(self.greeting))  # pyright: ignore[reportReturnType]
        return cls()


class GreetHandler:
    def __init__(self, greeter: Greeter | None = None) -> None:
        self.greeter = greeter or Greeter()

    async def handle(self, request: Greet) -> str:
        return f"{self.greeter.greeting} {request.name}"


async def test_default_resolver_instantiates_handlers_with_no_arguments() -> None:
    m = Mediator()
    m.register(Greet, GreetHandler)
    assert await m.send(Greet("ada")) == "hello ada"


async def test_a_custom_resolver_supplies_handler_instances() -> None:
    resolver = RecordingResolver()
    m = Mediator(resolver=resolver)
    m.register(Greet, GreetHandler)
    assert await m.send(Greet("ada")) == "hi ada"
    await m.send(Greet("ada"))
    assert resolver.resolved == [GreetHandler, GreetHandler]


async def test_resolvers_can_be_async() -> None:
    class AsyncResolver:
        async def resolve(self, cls: type[T]) -> T:
            await asyncio.sleep(0)
            return RecordingResolver("hey").resolve(cls)

    m = Mediator(resolver=AsyncResolver())
    m.register(Greet, GreetHandler)
    assert await m.send(Greet("ada")) == "hey ada"


async def test_a_singleton_handler_is_resolved_once_per_mediator() -> None:
    @handler(lifetime="singleton")
    class Counting:
        def __init__(self) -> None:
            self.calls = 0

        async def handle(self, request: Greet) -> str:
            self.calls += 1
            return str(self.calls)

    first, second = Mediator(), Mediator()
    first.register(Greet, Counting)
    second.register(Greet, Counting)
    assert [await first.send(Greet("x")) for _ in range(3)] == ["1", "2", "3"]
    assert await second.send(Greet("x")) == "1"


async def test_concurrent_first_sends_share_one_singleton() -> None:
    instances: list[object] = []

    @handler(lifetime="singleton")
    class Slow:
        async def handle(self, request: Greet) -> str:
            instances.append(self)
            return "ok"

    class SlowResolver:
        async def resolve(self, cls: type[T]) -> T:
            await asyncio.sleep(0)
            return cls()

    m = Mediator(resolver=SlowResolver())
    m.register(Greet, Slow)
    await asyncio.gather(*(m.send(Greet("x")) for _ in range(3)))
    assert len({id(instance) for instance in instances}) == 1


def test_lifetime_must_be_known() -> None:
    with pytest.raises(ValueError, match="lifetime must be one of"):
        handler(lifetime="scoped")  # pyright: ignore[reportArgumentType]


async def test_function_handlers_get_dependencies_resolved_by_type() -> None:
    @handler
    async def greet(request: Greet, greeter: Greeter, /, *, clock: Clock) -> str:
        return f"{greeter.greeting} {request.name} at {clock.now}"

    resolver = RecordingResolver()
    m = Mediator(resolver=resolver)
    m.register(Greet, greet)
    assert await m.send(Greet("ada")) == "hi ada at noon"
    await m.send(Greet("ada"))
    assert resolver.resolved == [Greeter, Clock, Greeter, Clock]


async def test_function_handlers_can_name_their_request() -> None:
    @handler(Greet)
    async def greet(request, greeter: Greeter) -> str:  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
        return f"{greeter.greeting} {request.name}"  # pyright: ignore[reportUnknownMemberType]

    m = Mediator()
    m.register(Greet, greet)  # pyright: ignore[reportUnknownArgumentType]
    assert await m.send(Greet("ada")) == "hello ada"


async def test_scan_discovers_function_handlers(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from dataclasses import dataclass
                from mediary import Returns, handler, request

                @request
                @dataclass
                class Add(Returns[int]):
                    a: int
                    b: int

                class Calculator:
                    def add(self, a: int, b: int) -> int:
                        return a + b

                @handler
                async def add(request: Add, calculator: Calculator) -> int:
                    return calculator.add(request.a, request.b)
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    app: Any = __import__(f"{pkg}.app").app
    assert await m.send(app.Add(2, 3)) == 5


def test_a_function_and_a_class_cannot_both_handle_a_request() -> None:
    async def greet(request: Greet) -> str:
        return "fn"

    m = Mediator()
    m.register(Greet, greet)
    with pytest.raises(DuplicateHandler):
        m.register(Greet, GreetHandler)


def _sync(request: Greet) -> str:
    return "sync"


async def _no_params() -> str:
    return "none"


async def _keyword_request(*, request: Greet) -> str:
    return "kw"


async def _var_args(request: Greet, *deps: Greeter) -> str:
    return "var"


async def _unhinted_dependency(request: Greet, greeter) -> str:  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
    return "unhinted"


@handler(lifetime="singleton")
async def _singleton_function(request: Greet) -> str:
    return "singleton"


INVALID_FUNCTIONS: list[tuple[Callable[..., Any], str]] = [
    (_sync, "`async def` function"),
    (_no_params, "must take positional parameters \\(request\\)"),
    (_keyword_request, "must take positional parameters \\(request\\)"),
    (_var_args, "resolved one by one"),
    (_unhinted_dependency, "`greeter` needs a type hint"),
    (_singleton_function, "only class handlers have a lifetime"),
]


@pytest.mark.parametrize(("function", "reason"), INVALID_FUNCTIONS)
def test_invalid_function_handlers_are_rejected(function: Callable[..., Any], reason: str) -> None:
    with pytest.raises(InvalidHandlerSignature, match=reason):
        Mediator().register(Greet, function)


def test_function_handler_types_are_kept() -> None:
    async def greet(request: Greet) -> str:
        return "hi"

    decorated: Callable[[Greet], Awaitable[str]] = handler(greet)
    assert decorated is greet
