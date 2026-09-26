import enum
from collections.abc import AsyncIterator
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any

import pytest

from mediary import (
    HandlerNotFound,
    Mediator,
    Next,
    NextStream,
    Returns,
    Yields,
    handler,
    notification,
    request,
    stream_request,
)
from mediary.testing import RecordingMediator

# The example from the `mediary.testing` docs.


class Plan(enum.Enum):
    FREE = "free"
    PRO = "pro"


@request
@dataclass(frozen=True)
class GetPlan(Returns[Plan]):
    email: str


@request
@dataclass(frozen=True)
class Register(Returns[None]):
    email: str


@notification
@dataclass(frozen=True)
class Welcomed:
    email: str


class RegisterUser:
    def __init__(self, mediator: Mediator) -> None:
        self.mediator = mediator

    async def handle(self, request: Register) -> None:
        if await self.mediator.send(GetPlan(request.email)) is Plan.FREE:
            await self.mediator.publish(Welcomed(request.email))


def register_user(mediator: Mediator) -> Any:
    @handler
    async def register(request: Register) -> None:
        await RegisterUser(mediator).handle(request)

    return register


async def test_registering_welcomes_the_user(mediator: RecordingMediator) -> None:
    mediator.register(Register, register_user(mediator))
    mediator.stub(GetPlan, Plan.FREE)

    await mediator.send(Register("ada@example.com"))

    assert mediator.published_of(Welcomed) == [Welcomed("ada@example.com")]


# The fixture and the plugin.


def test_the_plugin_is_registered_through_its_entry_point() -> None:
    (plugin,) = [e for e in entry_points(group="pytest11") if e.name == "mediary"]
    assert plugin.value == "mediary.pytest_plugin"


@pytest.fixture
def project(pytester: pytest.Pytester) -> pytest.Pytester:
    """A fresh pytest project, which loads installed plugins through their entry points."""
    pytester.makeini("[pytest]\nasyncio_default_fixture_loop_scope = function\n")
    return pytester


def test_each_test_gets_a_new_empty_mediator(mediator: RecordingMediator) -> None:
    assert isinstance(mediator, Mediator)
    assert (mediator.sent, mediator.published, mediator.streamed) == ([], [], [])


def test_a_fixture_of_your_own_takes_precedence(project: pytest.Pytester) -> None:
    project.makeconftest(
        """
        import pytest
        from mediary.testing import RecordingMediator

        @pytest.fixture
        def mediator():
            m = RecordingMediator()
            m.custom = True
            return m
        """
    )
    project.makepyfile(
        """
        def test_custom(mediator):
            assert mediator.custom
        """
    )
    project.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=1)


def test_the_fixture_works_in_a_fresh_project(project: pytest.Pytester) -> None:
    project.makepyfile(
        """
        from mediary.testing import RecordingMediator

        def test_fixture(mediator):
            assert type(mediator) is RecordingMediator
        """
    )
    project.runpytest("-p", "no:cacheprovider").assert_outcomes(passed=1)
    # Disabled by its entry point name, the fixture is gone: the entry point provided it.
    project.runpytest("-p", "no:cacheprovider", "-p", "no:mediary").assert_outcomes(errors=1)


# Recording and stubbing.


async def test_everything_sent_or_published_is_recorded_in_order() -> None:
    m = RecordingMediator()
    m.stub(GetPlan, Plan.PRO)
    await m.send(GetPlan("a"))
    await m.publish(Welcomed("b"))
    with pytest.raises(HandlerNotFound):
        await m.send(Register("c"))
    await m.send(GetPlan("d"))
    assert m.sent == [GetPlan("a"), Register("c"), GetPlan("d")]
    assert m.sent_of(GetPlan) == [GetPlan("a"), GetPlan("d")]
    assert m.published == m.published_of(Welcomed) == [Welcomed("b")]
    assert m.published_of(GetPlan) == []


async def test_a_stub_replaces_the_handler_and_can_fail() -> None:
    async def get_plan(request: GetPlan) -> Plan:
        raise AssertionError("the stub answers instead")

    m = RecordingMediator()
    m.register(GetPlan, get_plan)
    m.stub(GetPlan, Plan.FREE)
    assert await m.send(GetPlan("a")) is Plan.FREE
    m.stub(GetPlan, raises=LookupError("no such user"))
    with pytest.raises(LookupError, match="no such user"):
        await m.send(GetPlan("a"))


async def test_unstubbed_requests_go_to_their_handler() -> None:
    async def get_plan(request: GetPlan) -> Plan:
        return Plan.PRO

    m = RecordingMediator()
    m.register(GetPlan, get_plan)
    assert await m.send(GetPlan("a")) is Plan.PRO


async def test_behaviors_still_wrap_stubbed_requests() -> None:
    seen: list[str] = []

    async def spy(request: object, next: Next[Any]) -> Any:
        result = await next()
        seen.append(f"{type(request).__name__} -> {result}")
        return result

    m = RecordingMediator()
    m.use(spy)
    m.stub(GetPlan, Plan.PRO)
    await m.send(GetPlan("a"))
    assert seen == ["GetPlan -> Plan.PRO"]


async def test_recording_mediators_are_isolated() -> None:
    async def get_plan(request: GetPlan) -> Plan:
        return Plan.PRO

    first = RecordingMediator()
    first.register(GetPlan, get_plan)
    with pytest.raises(HandlerNotFound):
        await RecordingMediator().send(GetPlan("a"))


# Streams.


@stream_request
@dataclass(frozen=True)
class ListUsers(Yields[str]):
    plan: Plan


async def list_users(request: ListUsers) -> AsyncIterator[str]:
    yield "from the handler"


async def test_streams_are_recorded_and_can_be_stubbed(mediator: RecordingMediator) -> None:
    mediator.register(ListUsers, list_users)
    mediator.stub(ListUsers, ["ada", "grace"])

    assert [user async for user in mediator.stream(ListUsers(Plan.PRO))] == ["ada", "grace"]
    assert [user async for user in mediator.stream(ListUsers(Plan.FREE))] == ["ada", "grace"]
    assert mediator.streamed_of(ListUsers) == [ListUsers(Plan.PRO), ListUsers(Plan.FREE)]
    assert mediator.streamed_of(GetPlan) == []


async def test_unstubbed_streams_reach_their_handler(mediator: RecordingMediator) -> None:
    mediator.register(ListUsers, list_users)
    assert [user async for user in mediator.stream(ListUsers(Plan.PRO))] == ["from the handler"]
    with pytest.raises(HandlerNotFound):
        mediator.stream(Welcomed("x"))
    assert mediator.streamed == [ListUsers(Plan.PRO), Welcomed("x")]


async def test_a_stubbed_stream_can_fail_and_is_wrapped_by_behaviors(
    mediator: RecordingMediator,
) -> None:
    async def upper(request: ListUsers, next: NextStream[str]) -> AsyncIterator[str]:
        async for user in next():
            yield user.upper()

    mediator.use(upper)
    mediator.stub(ListUsers, ["ada"])
    assert [user async for user in mediator.stream(ListUsers(Plan.PRO))] == ["ADA"]

    mediator.stub(ListUsers, raises=ConnectionError("down"))
    stream = mediator.stream(ListUsers(Plan.PRO))
    with pytest.raises(ConnectionError, match="down"):
        await anext(stream)
