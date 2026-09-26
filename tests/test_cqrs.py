from dataclasses import dataclass
from typing import Any

import pytest
from conftest import MakePackage

from mediary import DuplicateHandler, Mediator, Next, RuleViolation, ScanError, handler
from mediary.cqrs import Command, Query, command, event, query


@command
@dataclass(frozen=True)
class Rename(Command[None]):
    user_id: int
    name: str


@query
@dataclass(frozen=True)
class GetName(Query[str]):
    user_id: int


@event
@dataclass(frozen=True)
class Renamed:
    user_id: int


class Users:
    names: dict[int, str] = {}  # noqa: RUF012


def make_mediator(*behaviors: Any) -> Mediator:
    m = Mediator()

    @handler
    async def rename(command: Rename) -> None:
        Users.names[command.user_id] = command.name
        await m.publish(Renamed(command.user_id))

    @handler
    async def get_name(query: GetName) -> str:
        return Users.names[query.user_id]

    m.register(Rename, rename)
    m.register(GetName, get_name)
    for b in behaviors:
        m.use(b[0], kinds=b[1])
    return m


def tracing(log: list[str], label: str) -> Any:
    async def trace(message: object, next: Next[Any]) -> Any:
        log.append(f"{label} {type(message).__name__}")
        return await next()

    trace.__qualname__ = label
    return trace


async def test_commands_queries_and_events_are_dispatched() -> None:
    log: list[str] = []

    async def audit(event: Renamed) -> None:
        log.append(f"renamed {event.user_id}")

    m = make_mediator()
    m.register(Renamed, audit)
    await m.send(Rename(1, "ada"))
    assert await m.send(GetName(1)) == "ada"
    assert log == ["renamed 1"]


async def test_behaviors_can_target_each_kind() -> None:
    log: list[str] = []
    m = make_mediator(
        (tracing(log, "command"), {"command"}),
        (tracing(log, "query"), {"query"}),
        (tracing(log, "event"), {"event"}),
    )
    await m.send(Rename(1, "ada"))
    await m.send(GetName(1))
    assert log == ["command Rename", "event Renamed", "query GetName"]


def test_commands_and_queries_have_exactly_one_handler() -> None:
    async def another(query: GetName) -> str:
        return ""

    with pytest.raises(DuplicateHandler):
        make_mediator().register(GetName, another)


def test_a_query_handler_must_return_something() -> None:
    class Nothing:
        async def handle(self, query: GetName) -> None:
            pass

    with pytest.raises(RuleViolation, match="a query handler must return what it read"):
        Mediator().register(GetName, Nothing)


async def test_command_handlers_may_return_nothing() -> None:
    async def rename(command: Rename) -> None:
        pass

    m = Mediator()
    m.register(Rename, rename)
    assert await m.send(Rename(1, "x")) is None


def test_the_base_must_match_the_decorator() -> None:
    with pytest.raises(TypeError, match="subclasses Query, so decorate it with @query"):

        @command
        class Wrong(Query[int]):
            pass

    with pytest.raises(TypeError, match="subclasses Command, so decorate it with @command"):

        @query
        class AlsoWrong(Command[int]):
            pass


def test_scan_reports_every_rule_violation(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from mediary import handler
                from mediary.cqrs import Command, Query, command, query

                @query
                class First(Query[int]):
                    pass

                @query
                class Second(Query[int]):
                    pass

                @command
                class Save(Command[None]):
                    pass

                @handler
                async def first(query: First) -> None: ...

                @handler
                async def second(query: Second) -> None: ...

                @handler
                async def save(command: Save) -> None: ...

                @handler(Save)
                async def save_again(command: Save) -> None: ...
            """
        }
    )
    with pytest.raises(ScanError) as exc:
        Mediator().scan(pkg)
    assert [type(e) for e in exc.value.errors] == [RuleViolation, RuleViolation, DuplicateHandler]
