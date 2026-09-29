from dataclasses import dataclass

import pytest

from mediary import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidHandlerSignature,
    MediaryError,
    Mediator,
    NotARequest,
    Returns,
    request,
)


@dataclass(frozen=True)
class User:
    id: int
    name: str


@request
@dataclass(frozen=True)
class GetUser(Returns[User]):
    user_id: int


class GetUserHandler:
    async def handle(self, request: GetUser) -> User:
        return User(request.user_id, "ada")


@request
@dataclass(frozen=True)
class RenameUser(Returns[None]):
    user_id: int
    name: str


renamed: list[RenameUser] = []


class RenameUserHandler:
    async def handle(self, request: RenameUser) -> None:
        renamed.append(request)


@request
class Ping:
    pass


class PingHandler:
    async def handle(self, request: Ping) -> str:
        return "pong"


@pytest.fixture
def mediator() -> Mediator:
    m = Mediator()
    m.register(GetUser, GetUserHandler)
    m.register(RenameUser, RenameUserHandler)
    m.register(Ping, PingHandler)
    return m


async def test_send_returns_the_handler_result(mediator: Mediator) -> None:
    assert await mediator.send(GetUser(7)) == User(7, "ada")


async def test_command_without_result_returns_none(mediator: Mediator) -> None:
    command = RenameUser(7, "grace")
    assert await mediator.send(command) is None
    assert renamed[-1] is command


async def test_request_without_returns_still_dispatches(mediator: Mediator) -> None:
    assert await mediator.send(Ping()) == "pong"


async def test_a_new_handler_instance_serves_each_send() -> None:
    seen: list[int] = []

    class Counting:
        async def handle(self, request: Ping) -> str:
            seen.append(id(self))
            return "pong"

    m = Mediator()
    m.register(Ping, Counting)
    await m.send(Ping())
    await m.send(Ping())
    assert len(seen) == 2


async def test_unregistered_request_raises_handler_not_found() -> None:
    with pytest.raises(HandlerNotFound, match=r"test_send\.GetUser.*@request") as exc:
        await Mediator().send(GetUser(1))
    assert exc.value.request_type is GetUser
    assert isinstance(exc.value, MediaryError)
    assert isinstance(exc.value, LookupError)


async def test_dispatch_is_by_exact_type(mediator: Mediator) -> None:
    @request
    @dataclass(frozen=True)
    class GetAdmin(GetUser):
        pass

    with pytest.raises(HandlerNotFound):
        await mediator.send(GetAdmin(1))


async def test_mediators_do_not_share_registrations(mediator: Mediator) -> None:
    with pytest.raises(HandlerNotFound):
        await Mediator().send(Ping())
    assert await mediator.send(Ping()) == "pong"


def test_registering_a_second_handler_is_rejected(mediator: Mediator) -> None:
    class OtherPingHandler:
        async def handle(self, request: Ping) -> str:
            return "other"

    with pytest.raises(DuplicateHandler, match="exactly one handler") as exc:
        mediator.register(Ping, OtherPingHandler)
    assert (exc.value.existing, exc.value.duplicate) == (PingHandler, OtherPingHandler)


def test_handlers_can_only_be_registered_for_requests() -> None:
    class NotMarked:
        pass

    class Handler:
        async def handle(self, request: NotMarked) -> None: ...

    with pytest.raises(NotARequest, match="Decorate it with @request"):
        Mediator().register(NotMarked, Handler)


def test_subclasses_of_a_request_are_not_requests_unless_decorated() -> None:
    @dataclass(frozen=True)
    class GetAdmin(GetUser):
        pass

    with pytest.raises(NotARequest):
        Mediator().register(GetAdmin, GetUserHandler)


@pytest.mark.parametrize(
    "handler",
    [type("NoHandle", (), {}), type("NotAMethod", (), {"handle": "pong"})],
)
def test_handlers_need_a_handle_method(handler: type) -> None:
    with pytest.raises(InvalidHandlerSignature, match=r"a `handle\(self, request\)` method"):
        Mediator().register(Ping, handler)
