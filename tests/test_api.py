"""The public API decided in the pre-1.0 review (#41): new contracts, and the deprecated names."""

import warnings
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any, assert_type

import pytest
from conftest import MakePackage

import mediary
from mediary import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidBehavior,
    InvalidHandler,
    Mediator,
    Next,
    NotAMessage,
    NotANotification,
    NotificationCall,
    Publisher,
    Returns,
    RuleViolation,
    ScanError,
    Sender,
    Yields,
    behavior,
    notification,
    request,
    stream_request,
)
from mediary.cqrs import Query, command, query
from mediary.testing import RecordingMediator


@request
@dataclass(frozen=True)
class GetUser(Returns[str]):
    user_id: int


@stream_request
@dataclass(frozen=True)
class Count(Yields[int]):
    up_to: int


@notification
@dataclass(frozen=True)
class Renamed:
    name: str


@query
class Lookup(Query[int]):
    pass


@command
class Rename:
    pass


async def get_user(request: GetUser) -> str:
    return "ada"


async def count(request: Count) -> AsyncIterator[int]:
    for n in range(request.up_to):
        yield n


async def email(event: Renamed) -> None:
    pass


async def audit(event: Renamed) -> None:
    pass


# Sender and Publisher


async def greet(sender: Sender, publisher: Publisher) -> list[object]:
    name = assert_type(await sender.send(GetUser(1)), str)
    async with sender.stream(Count(2)) as numbers:
        counted = [n async for n in numbers]
    await publisher.publish(Renamed(name))
    return [name, counted]


async def test_a_mediator_is_a_sender_and_a_publisher() -> None:
    m = RecordingMediator()
    m.register(GetUser, get_user)
    m.register(Count, count)
    assert await greet(m, m) == ["ada", [0, 1]]
    assert m.published == [Renamed("ada")]


# NotificationCall


class Recording:
    def __init__(self) -> None:
        self.seen: list[tuple[Any, object]] = []

    async def publish(self, calls: Sequence[NotificationCall], /) -> None:
        for call in calls:
            self.seen.append((call.handler, call.notification))
            await call()


async def test_a_strategy_sees_each_handler_and_the_notification() -> None:
    strategy = Recording()
    m = Mediator(publish_strategy=strategy)
    m.register(Renamed, email)
    m.register(Renamed, audit)
    await m.publish(Renamed("ada"))
    assert strategy.seen == [(audit, Renamed("ada")), (email, Renamed("ada"))]


async def test_a_notification_call_runs_its_handler() -> None:
    ran: list[str] = []

    async def run() -> str:
        ran.append("ran")
        return "discarded"

    call = NotificationCall(email, Renamed("ada"), run)
    assert await call() is None
    assert ran == ["ran"]
    assert "run" not in repr(call)


# kinds=


async def passthrough(message: object, next: Next[Any]) -> Any:
    return await next()


def test_kinds_must_be_defined() -> None:
    with pytest.raises(InvalidBehavior, match="names no defined kind: 'comand'") as exc:
        Mediator().use(passthrough, kinds={"command", "comand"})
    assert exc.value.reason == "`kinds` names no defined kind: 'comand'"


def test_a_scanned_behavior_with_an_unknown_kind_is_a_scan_problem(
    make_package: MakePackage,
) -> None:
    pkg = make_package(
        {
            "behaviors.py": """
                from mediary import behavior

                @behavior(kinds={"querry"})
                async def cache(message: object, next): return await next()
            """
        }
    )
    with pytest.raises(ScanError) as exc:
        Mediator().scan(pkg)
    assert [type(e) for e in exc.value.errors] == [InvalidBehavior]


def test_kinds_must_be_a_collection() -> None:
    with pytest.raises(TypeError, match="collection of kind names"):
        behavior(kinds="query")


# Errors


def test_errors_name_the_message_type() -> None:
    m = Mediator()
    m.register(GetUser, get_user)
    with pytest.raises(NotAMessage) as not_a_message:
        m.register(int, get_user)  # pyright: ignore[reportArgumentType]
    assert not_a_message.value.message_type is int
    with pytest.raises(DuplicateHandler) as duplicate:
        m.register(GetUser, lambda r: "")
    assert duplicate.value.message_type is GetUser


async def test_errors_raised_on_dispatch_name_the_message_type() -> None:
    with pytest.raises(HandlerNotFound) as not_found:
        await Mediator().send(GetUser(1))
    assert not_found.value.message_type is GetUser
    with pytest.raises(NotANotification) as not_notification:
        await Mediator().publish(GetUser(1))
    assert not_notification.value.message_type is GetUser


def test_errors_say_why_a_handler_is_rejected() -> None:
    with pytest.raises(InvalidHandler) as invalid:
        Mediator().register(GetUser, 42)  # pyright: ignore[reportArgumentType]
    assert invalid.value.handler == 42
    assert invalid.value.reason == "it needs to be a function or a class"

    async def reads_nothing(query: Lookup) -> None: ...

    with pytest.raises(RuleViolation) as violation:
        Mediator().register(Lookup, reads_nothing)
    assert violation.value.kind == "query"
    assert violation.value.message_type is Lookup
    assert "annotated to return None" in violation.value.reason


# Deprecated names: each still works, with a warning that names its replacement


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("NotARequest", NotAMessage),
        ("InvalidHandlerSignature", InvalidHandler),
        ("InvalidBehaviorSignature", InvalidBehavior),
    ],
)
def test_deprecated_error_names_are_the_new_classes(old: str, new: type[Exception]) -> None:
    with pytest.warns(DeprecationWarning, match=rf"mediary\.{old} .*use mediary\.{new.__name__}"):
        assert getattr(mediary, old) is new
    assert old not in mediary.__all__


def test_catching_an_old_name_catches_the_new_error() -> None:
    with pytest.warns(DeprecationWarning, match="NotARequest"):
        from mediary import NotARequest  # pyright: ignore[reportDeprecated]

    with pytest.raises(NotARequest):  # pyright: ignore[reportDeprecated]
        Mediator().register(int, get_user)  # pyright: ignore[reportArgumentType]


def test_unknown_names_are_still_missing() -> None:
    with pytest.raises(AttributeError, match="has no attribute 'Nope'"):
        getattr(mediary, "Nope")  # noqa: B009 - an attribute the type checker would reject


def test_deprecated_error_attributes_read_the_new_ones() -> None:
    errors: list[tuple[Exception, str]] = [
        (HandlerNotFound(GetUser), "request_type"),
        (DuplicateHandler(GetUser, get_user, count), "request_type"),
        (NotAMessage(GetUser), "cls"),
        (NotANotification(GetUser), "cls"),
    ]
    for error, old in errors:
        with pytest.warns(DeprecationWarning, match=rf"\.{old} is deprecated.*\.message_type"):
            assert getattr(error, old) is GetUser


async def test_register_takes_its_old_keywords_with_a_warning() -> None:
    m = Mediator()
    with pytest.warns(DeprecationWarning, match="passing request_type, handler to"):
        m.register(request_type=GetUser, handler=get_user)  # pyright: ignore[reportCallIssue]
    with pytest.warns(DeprecationWarning, match="passing handler to"):
        m.register(Count, handler=count)  # pyright: ignore[reportCallIssue]
    assert await m.send(GetUser(1)) == "ada"


async def test_the_recorded_messages_take_their_old_keywords_with_a_warning() -> None:
    m = RecordingMediator()
    m.stub(GetUser, "ada")
    await m.send(GetUser(1))
    await m.publish(Renamed("ada"))
    with pytest.warns(DeprecationWarning, match="passing request_type to"):
        assert m.sent_of(request_type=GetUser) == [GetUser(1)]  # pyright: ignore[reportCallIssue]
    with pytest.warns(DeprecationWarning, match="passing notification_type to"):
        assert m.published_of(notification_type=Renamed) == [Renamed("ada")]  # pyright: ignore[reportCallIssue]
    with pytest.warns(DeprecationWarning, match="passing request_type to"):
        assert m.streamed_of(request_type=Count) == []  # pyright: ignore[reportCallIssue]


def test_positional_calls_do_not_warn() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        m = RecordingMediator()
        m.register(GetUser, get_user)
        assert m.sent_of(GetUser) == []


def test_a_keyword_that_cannot_move_is_still_an_error() -> None:
    with pytest.raises(TypeError, match="'handler'"):
        Mediator().register(handler=get_user)  # pyright: ignore[reportCallIssue]
