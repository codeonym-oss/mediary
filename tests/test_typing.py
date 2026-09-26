"""
Type-level tests: pyright (strict) checks this file in CI.

`assert_type` fails type checking if the inferred type differs; each
`pyright: ignore[...]` asserts an error IS reported (unused ignores are errors).
"""

from dataclasses import dataclass
from typing import Any, TypeVar, assert_type

from mediary import Mediator, Next, Returns, behavior, handler, request

T = TypeVar("T")


@request
@dataclass
class GetName(Returns[str]):
    user_id: int


@request
@dataclass
class Delete(Returns[None]):
    user_id: int


@request
class Untyped:
    pass


class GetNameHandler:
    async def handle(self, request: GetName) -> str:
        return "ada"


class DeleteHandler:
    async def handle(self, request: Delete) -> None:
        return None


class UntypedHandler:
    async def handle(self, request: Untyped) -> int:
        return 1


async def test_send_is_typed_from_returns() -> None:
    m = Mediator()
    m.register(GetName, GetNameHandler)
    m.register(Delete, DeleteHandler)
    m.register(Untyped, UntypedHandler)

    assert_type(await m.send(GetName(1)), str)
    assert_type(await m.send(Delete(1)), None)
    assert_type(await m.send(Untyped()), Any)


def test_register_rejects_a_handler_for_another_request() -> None:
    # Registration doesn't inspect hints at runtime, so only the static error is under test.
    Mediator().register(GetName, DeleteHandler)  # pyright: ignore[reportArgumentType]


def test_handler_keeps_the_decorated_class_type() -> None:
    assert_type(handler(GetNameHandler), type[GetNameHandler])
    assert_type(handler(GetName)(GetNameHandler), type[GetNameHandler])


async def get_name(request: GetName, other: Untyped) -> str:
    return "ada"


def test_register_accepts_matching_function_handlers() -> None:
    Mediator().register(GetName, get_name)
    Mediator().register(Delete, get_name)  # pyright: ignore[reportArgumentType]


class Passthrough:
    async def handle(self, request: object, next: Next[T]) -> T:
        return await next()


async def passthrough(request: object, next: Next[T]) -> T:
    return await next()


def test_behavior_keeps_the_decorated_type() -> None:
    assert_type(behavior(Passthrough), type[Passthrough])
    assert_type(behavior(order=1)(Passthrough), type[Passthrough])
    Mediator().use(behavior(passthrough))
