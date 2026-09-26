"""
Type-level tests: pyright (strict) checks this file in CI.

`assert_type` fails type checking if the inferred type differs; each
`pyright: ignore[...]` asserts an error IS reported (unused ignores are errors).
"""

from dataclasses import dataclass
from typing import Any, TypeVar, assert_type

import pytest

from mediary import Mediator, Next, Returns, behavior, handler, request, retryable
from mediary.cqrs import Command, CommandSender, Query, QuerySender, command, query

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


@command
@dataclass
class Rename(Command[None]):
    name: str


@query
@dataclass
class CountUsers(Query[int]):
    pass


async def rename(request: Rename) -> None:
    pass


async def count_users(request: CountUsers) -> int:
    return 1


async def use_senders(commands: CommandSender, queries: QuerySender) -> None:
    assert_type(await queries.send(CountUsers()), int)
    assert_type(await commands.send(Rename("ada")), None)
    # Each is sent all the same at runtime; only the static errors are under test.
    await queries.send(Rename("ada"))  # pyright: ignore[reportArgumentType]
    await commands.send(CountUsers())  # pyright: ignore[reportArgumentType]


async def test_a_mediator_is_both_senders_and_each_sends_only_its_kind() -> None:
    m = Mediator()
    m.register(Rename, rename)
    m.register(CountUsers, count_users)
    await use_senders(m, m)
    assert_type(command(Rename), type[Rename])


class Flaky(Exception):
    pass


def test_retryable_keeps_the_exception_type() -> None:
    assert_type(retryable(Flaky), type[Flaky])
    with pytest.raises(TypeError):
        retryable(int)  # pyright: ignore[reportArgumentType]
