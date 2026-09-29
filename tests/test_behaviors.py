from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

import pytest
from conftest import MakePackage

from mediary import (
    HandlerNotFound,
    InvalidBehavior,
    Mediator,
    Next,
    Returns,
    ScanError,
    behavior,
    request,
)

T = TypeVar("T")


class HasUserId(Protocol):
    user_id: int


class Describes(Protocol):
    def describe(self) -> str: ...


@request
@dataclass(frozen=True)
class GetUser(Returns[str]):
    user_id: int


@request
@dataclass(frozen=True)
class GetAdmin(GetUser):
    pass


@request
@dataclass(frozen=True)
class Ping(Returns[str]):
    def describe(self) -> str:
        return "ping"


async def get_user(request: GetUser) -> str:
    return f"user {request.user_id}"


async def get_admin(request: GetAdmin) -> str:
    return f"admin {request.user_id}"


async def ping(request: Ping) -> str:
    return "pong"


def make_mediator(*behaviors: Callable[..., Any]) -> Mediator:
    m = Mediator()
    m.register(GetUser, get_user)
    m.register(GetAdmin, get_admin)
    m.register(Ping, ping)
    for b in behaviors:
        m.use(b)
    return m


def tagging(tag: str, **options: Any) -> Any:
    """A function behavior, targeting `hint`, that appends `tag` to the result."""
    hint = options.pop("hint", object)

    async def tag_result(request: Any, next: Next[str]) -> str:
        return f"{await next()} [{tag}]"

    tag_result.__annotations__["request"] = hint
    tag_result.__qualname__ = f"tagging.{tag}"
    return behavior(**options)(tag_result)


async def test_a_class_behavior_wraps_the_handler() -> None:
    calls: list[str] = []

    class Tracing:
        async def handle(self, request: object, next: Next[T]) -> T:
            calls.append("before")
            result = await next()
            calls.append("after")
            return result

    m = make_mediator(Tracing)
    assert await m.send(GetUser(1)) == "user 1"
    assert calls == ["before", "after"]


async def test_behaviors_can_short_circuit_and_retry() -> None:
    attempts: list[int] = []

    async def flaky(request: Ping) -> str:
        attempts.append(1)
        if len(attempts) < 2:
            raise ConnectionError
        return "pong"

    async def retry(request: Ping, next: Next[str]) -> str:
        try:
            return await next()
        except ConnectionError:
            return await next()

    async def cached(request: GetUser, next: Next[str]) -> str:
        return "cached"

    m = Mediator()
    m.register(Ping, flaky)
    m.register(GetUser, get_user)
    m.use(retry)
    m.use(cached)
    assert await m.send(Ping()) == "pong"
    assert len(attempts) == 2
    assert await m.send(GetUser(1)) == "cached"


async def test_behaviors_are_resolved_per_send_with_their_dependencies() -> None:
    resolved: list[type] = []

    class Prefix:
        text = ">"

    class Resolver:
        def resolve(self, cls: type[T]) -> T:
            resolved.append(cls)
            return cls()

    class Wrapping:
        async def handle(self, request: object, next: Next[str]) -> str:
            return f"({await next()})"

    async def prefixed(request: object, next: Next[str], prefix: Prefix) -> str:
        return prefix.text + await next()

    m = Mediator(resolver=Resolver())
    m.register(Ping, ping)
    m.use(Wrapping, order=1)
    m.use(prefixed, order=2)
    assert await m.send(Ping()) == "(>pong)"
    await m.send(Ping())
    assert resolved == [Wrapping, Prefix, Wrapping, Prefix]


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        (object, {"user 1 [t]", "admin 1 [t]", "pong [t]"}),
        (Any, {"user 1 [t]", "admin 1 [t]", "pong [t]"}),
        (GetUser, {"user 1 [t]", "admin 1 [t]", "pong"}),
        (GetAdmin, {"user 1", "admin 1 [t]", "pong"}),
        (HasUserId, {"user 1 [t]", "admin 1 [t]", "pong"}),
        (Describes, {"user 1", "admin 1", "pong [t]"}),
        (GetAdmin | Ping, {"user 1", "admin 1 [t]", "pong [t]"}),
    ],
)
async def test_behaviors_wrap_the_requests_their_hint_matches(
    hint: Any, expected: set[str]
) -> None:
    m = make_mediator(tagging("t", hint=hint))
    assert {await m.send(GetUser(1)), await m.send(GetAdmin(1)), await m.send(Ping())} == expected


async def test_behaviors_without_a_request_hint_wrap_everything() -> None:
    async def untyped(request, next):  # pyright: ignore[reportMissingParameterType, reportUnknownParameterType]
        return f"{await next()}!"

    m = make_mediator(untyped)  # pyright: ignore[reportUnknownArgumentType]
    assert await m.send(Ping()) == "pong!"


async def test_behaviors_can_target_request_kinds() -> None:
    m = make_mediator(tagging("mine", kinds={"request"}), tagging("other", kinds={"command"}))
    assert await m.send(Ping()) == "pong [mine]"


def test_kinds_must_be_a_collection() -> None:
    with pytest.raises(TypeError, match=r"like \{'request'\}"):
        behavior(kinds="request")


async def test_lower_order_runs_outside_and_ties_break_by_name() -> None:
    # Added in reverse: order decides first, then the fully qualified name.
    m = make_mediator(
        tagging("b", order=1), tagging("a", order=1), tagging("z", order=0), tagging("y", order=2)
    )
    assert await m.send(Ping()) == "pong [y] [b] [a] [z]"


async def test_use_overrides_the_decorator_and_ignores_repeats() -> None:
    first, second = tagging("first", order=1), tagging("second", order=2)
    m = make_mediator(first)
    m.use(second, order=0)
    m.use(first, order=5)
    assert await m.send(Ping()) == "pong [first] [second]"


async def test_the_pipeline_is_computed_once_per_request_type() -> None:
    checks: list[type] = []

    class Counting(type):
        def __subclasscheck__(cls, subclass: type) -> bool:
            checks.append(subclass)
            return False

    class Target(metaclass=Counting):
        pass

    m = make_mediator(tagging("t", hint=Target))
    for _ in range(3):
        await m.send(Ping())
    assert checks == [Ping]

    m.use(tagging("new"))
    assert await m.send(Ping()) == "pong [new]"
    assert checks == [Ping, Ping]


async def test_behaviors_do_not_run_without_a_handler() -> None:
    ran: list[bool] = []

    async def spy(request: object, next: Next[Any]) -> Any:
        ran.append(True)
        return await next()

    @request
    class Unhandled:
        pass

    with pytest.raises(HandlerNotFound):
        await make_mediator(spy).send(Unhandled())
    assert ran == []


async def test_scan_adds_decorated_behaviors(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from mediary import Next, Returns, behavior, handler, request

                @request
                class Ping(Returns[str]):
                    pass

                @handler
                async def ping(request: Ping) -> str:
                    return "pong"

                @behavior(order=2)
                async def inner(request: object, next: Next[str]) -> str:
                    return f"<{await next()}>"

                @behavior(order=1, kinds={"request"})
                class Outer:
                    async def handle(self, request: Ping, next: Next[str]) -> str:
                        return f"[{await next()}]"
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    app: Any = __import__(f"{pkg}.app").app
    assert await m.send(app.Ping()) == "[<pong>]"


async def _no_next(request: object) -> None: ...


async def _keyword_next(request: object, *, next: Next[Any]) -> Any: ...


async def _generic_hint(request: list[int], next: Next[Any]) -> Any: ...


def _not_async(request: object, next: Next[Any]) -> Any: ...


class _NoHandle:
    pass


@pytest.mark.parametrize(
    ("invalid", "reason"),
    [
        (_no_next, r"positional parameters \(message, next\)"),
        (_keyword_next, r"positional parameters \(message, next\)"),
        (_generic_hint, "a class, a Protocol or a union"),
        (_not_async, "`async def` function"),
        (_NoHandle, r"async def handle\(self, message, next\)"),
    ],
)
def test_invalid_behaviors_are_rejected(invalid: Any, reason: str) -> None:
    with pytest.raises(InvalidBehavior, match=reason):
        Mediator().use(invalid)


def test_scan_reports_invalid_behaviors(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from mediary import behavior

                @behavior
                def not_async(request, next): ...

                @behavior
                class NoHandle: ...
            """
        }
    )
    with pytest.raises(ScanError) as exc:
        Mediator().scan(pkg)
    assert [type(e) for e in exc.value.errors] == [InvalidBehavior] * 2
