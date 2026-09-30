import dataclasses
from dataclasses import dataclass

import pytest
from conftest import MakePackage

from mediary import (
    BehaviorRegistration,
    HandlerRegistration,
    Mediator,
    Next,
    Registrations,
    behavior,
    handler,
    notification,
    request,
)
from mediary.behaviors import LoggingBehavior, RetryBehavior


@request
@dataclass(frozen=True)
class GetUser:
    user_id: int


@notification
@dataclass(frozen=True)
class UserRegistered:
    user_id: int


@handler(lifetime="singleton")
class GetUserHandler:
    async def handle(self, request: GetUser) -> str:
        return "ada"


async def send_welcome(event: UserRegistered) -> None:
    pass


async def audit(event: UserRegistered) -> None:
    pass


@behavior(order=5, kinds={"request"})
class Timing:
    async def handle(self, message: object, next: Next[object]) -> object:
        return await next()


async def tracing(message: object, next: Next[object]) -> object:
    return await next()


def test_a_new_mediator_has_no_registrations() -> None:
    assert Mediator().registrations() == Registrations()


def test_handlers_are_listed_by_message_type_then_in_publish_order() -> None:
    m = Mediator()
    m.register(UserRegistered, send_welcome)
    m.register(GetUser, GetUserHandler)
    m.register(UserRegistered, audit)
    assert m.registrations().handlers == (
        HandlerRegistration(GetUser, GetUserHandler, "singleton"),
        HandlerRegistration(UserRegistered, audit, "transient"),
        HandlerRegistration(UserRegistered, send_welcome, "transient"),
    )


def test_behaviors_are_listed_in_pipeline_order() -> None:
    m = Mediator()
    retry = RetryBehavior()
    m.use(Timing)
    m.use(retry, order=-1)
    m.use(tracing, kinds=["notification"])
    assert m.registrations().behaviors == (
        BehaviorRegistration(retry, -1, None),
        BehaviorRegistration(tracing, 0, frozenset({"notification"})),
        BehaviorRegistration(Timing, 5, frozenset({"request"})),
    )


def test_a_behavior_with_both_shapes_is_listed_for_each() -> None:
    m = Mediator()
    logging = LoggingBehavior()
    m.use(logging)
    assert {b.streams for b in m.registrations().behaviors if b.behavior is logging} == {
        False,
        True,
    }


def test_scanned_handlers_and_behaviors_are_listed(make_package: MakePackage) -> None:
    name = make_package(
        {
            "app.py": """
            from mediary import Next, behavior, handler, request

            @request
            class Ping:
                pass

            @handler
            async def ping(request: Ping) -> str:
                return "pong"

            @behavior
            async def around(message: object, next: Next[object]) -> object:
                return await next()
            """
        }
    )
    m = Mediator()
    m.scan(name)
    registrations = m.registrations()
    assert [h.handler.__name__ for h in registrations.handlers] == ["ping"]
    assert [h.message_type.__name__ for h in registrations.handlers] == ["Ping"]
    assert [b.behavior.__name__ for b in registrations.behaviors] == ["around"]


def test_registrations_are_a_frozen_snapshot() -> None:
    m = Mediator()
    before = m.registrations()
    m.register(GetUser, GetUserHandler)
    assert before.handlers == ()
    assert len(m.registrations().handlers) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        before.handlers = ()  # pyright: ignore[reportAttributeAccessIssue]


def test_a_view_shares_the_registrations_of_its_mediator() -> None:
    m = Mediator()
    view = m.with_resolver(m.resolver)
    m.register(GetUser, GetUserHandler)
    assert view.registrations() == m.registrations()
