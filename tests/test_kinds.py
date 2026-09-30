import inspect
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from mediary import (
    DuplicateHandler,
    Mediator,
    Next,
    NotAMessage,
    Returns,
    RuleViolation,
    request,
)
from mediary.behaviors import LoggingBehavior
from mediary.kinds import HandlerInfo, define_kind, kind_named, kind_of

seen: list[HandlerInfo] = []


def no_strings(info: HandlerInfo) -> str | None:
    seen.append(info)
    return "it must not return a str" if info.returns is str else None


def no_floats(info: HandlerInfo) -> str | None:
    return "it must not return a float" if info.returns is float else None


tally = define_kind("tally", dispatch="send", rules=[no_strings, no_floats])
alert = define_kind("alert", dispatch="publish")


@tally
@dataclass(frozen=True)
class Totals(Returns[int]):
    year: int


@alert
@dataclass(frozen=True)
class DiskFull:
    pass


def test_a_kind_decorates_a_class_as_itself() -> None:
    assert kind_of(Totals) is tally
    assert (tally.name, tally.dispatch) == ("tally", "send")
    assert kind_of(DiskFull) is alert
    assert kind_of(int) is None


def test_a_kind_is_looked_up_by_name() -> None:
    assert kind_named("tally") is tally

    @request
    class Ping:
        pass

    assert kind_named("request") is kind_of(Ping)
    assert kind_named("no such kind") is None


def test_a_kind_is_not_inherited() -> None:
    class Monthly(Totals):
        pass

    async def monthly(request: Monthly) -> int:
        return 0

    assert kind_of(Monthly) is None
    with pytest.raises(NotAMessage):
        Mediator().register(Monthly, monthly)


@pytest.mark.parametrize("name", ["tally", "request", "notification", "handler", "behavior"])
def test_kind_names_are_unique(name: str) -> None:
    with pytest.raises(ValueError, match=f"a kind named '{name}' is already defined"):
        define_kind(name, dispatch="send")


def test_dispatch_must_be_known() -> None:
    with pytest.raises(ValueError, match='"send", "publish" or "stream"'):
        define_kind("unknown_dispatch", dispatch="broadcast")  # pyright: ignore[reportArgumentType]


async def test_send_kinds_have_exactly_one_handler() -> None:
    async def totals(request: Totals) -> int:
        return request.year

    async def other(request: Totals) -> int:
        return 0

    m = Mediator()
    m.register(Totals, totals)
    assert await m.send(Totals(2026)) == 2026
    with pytest.raises(DuplicateHandler):
        m.register(Totals, other)


async def test_publish_kinds_have_any_number_of_handlers() -> None:
    log: list[str] = []

    async def page(event: DiskFull) -> None:
        log.append("page")

    async def email(event: DiskFull) -> None:
        log.append("email")

    m = Mediator()
    m.register(DiskFull, page)
    m.register(DiskFull, email)
    await m.publish(DiskFull())
    assert log == ["email", "page"]


def test_rules_see_the_handler_and_its_return_hint() -> None:
    class Handler:
        async def handle(self, request: Totals) -> int:
            return 0

    async def unannotated(request: Totals):
        return 0

    seen.clear()
    Mediator().register(Totals, Handler)
    Mediator().register(Totals, unannotated)
    assert seen == [
        HandlerInfo(Totals, Handler, int),
        HandlerInfo(Totals, unannotated, inspect.Signature.empty),
    ]


def test_a_handler_breaking_a_rule_is_rejected() -> None:
    async def as_text(request: Totals) -> str:
        return ""

    async def as_float(request: Totals) -> float:
        return 0.0

    with pytest.raises(RuleViolation, match="breaks a rule of @tally: it must not return a str"):
        Mediator().register(Totals, as_text)
    with pytest.raises(RuleViolation, match="it must not return a float"):
        Mediator().register(Totals, as_float)


async def test_behaviors_and_logging_know_the_kind(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="test.kinds")
    wrapped: list[str] = []

    async def tallies_only(message: object, next: Next[Any]) -> Any:
        wrapped.append(type(message).__name__)
        return await next()

    @request
    class Plain:
        pass

    async def totals(request: Totals) -> int:
        return 1

    async def plain(request: Plain) -> None:
        pass

    m = Mediator()
    m.register(Totals, totals)
    m.register(Plain, plain)
    m.use(tallies_only, kinds={"tally"})
    m.use(LoggingBehavior(logging.getLogger("test.kinds")))
    await m.send(Totals(1))
    await m.send(Plain())
    assert wrapped == ["Totals"]
    assert [r.__dict__["mediary_kind"] for r in caplog.records] == ["tally", "request"]
