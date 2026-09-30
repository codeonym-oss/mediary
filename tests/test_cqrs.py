from dataclasses import dataclass
from typing import Any

import pytest
from conftest import MakePackage

from mediary import DuplicateHandler, Mediator, Next, RuleViolation, ScanError, handler
from mediary.cqrs import (
    Command,
    Event,
    Query,
    command,
    command_behavior,
    command_handler,
    event,
    event_behavior,
    event_handler,
    query,
    query_handler,
)


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


@pytest.mark.parametrize(("base", "name"), [(Command[None], "command"), (Query[int], "query")])
def test_an_event_cannot_subclass_a_command_or_query(base: type[object], name: str) -> None:
    with pytest.raises(TypeError, match=f"subclasses {name.title()}, so decorate it with @{name}"):

        @event
        class Wrong(base):
            pass


@pytest.mark.parametrize("decorator", [command, query])
def test_a_command_or_query_cannot_subclass_event(decorator: Any) -> None:
    with pytest.raises(TypeError, match="subclasses Event, so decorate it with @event"):

        @decorator
        class Wrong(Event):
            pass


async def test_events_with_the_base_are_published() -> None:
    received: list[object] = []

    @event
    @dataclass(frozen=True)
    class Shipped(Event):
        order_id: int

    async def on_shipped(event: Shipped) -> None:
        received.append(event)

    m = Mediator()
    m.register(Shipped, on_shipped)
    await m.publish(Shipped(7))
    assert received == [Shipped(7)]


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


# Handler and behavior decorators of each kind


async def test_kind_handlers_register_and_scan_like_handler(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from mediary.cqrs import (
                    Command, Query, command, command_handler, event, event_handler, query,
                    query_handler,
                )

                seen = []

                @command
                class Save(Command[int]):
                    pass

                @query
                class Load(Query[str]):
                    pass

                @event
                class Saved:
                    pass

                @command_handler
                async def save(command: Save) -> int:
                    return 1

                @query_handler(lifetime="singleton")
                class LoadHandler:
                    async def handle(self, query: Load) -> str:
                        return "loaded"

                @event_handler
                def saved(event: Saved) -> None:  # sync, as @handler allows
                    seen.append("saved")
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    app = __import__(f"{pkg}.app", fromlist=["app"])
    assert await m.send(app.Save()) == 1
    assert await m.send(app.Load()) == "loaded"
    await m.publish(app.Saved())
    assert app.seen == ["saved"]


async def test_a_kind_handler_can_name_its_message() -> None:
    @command_handler(Rename)
    async def rename(command: object) -> None:
        pass

    m = Mediator()
    m.register(Rename, rename)
    assert await m.send(Rename(1, "ada")) is None


@pytest.mark.parametrize(
    ("decorate", "message", "wrong"),
    [
        (command_handler, GetName, "@query"),
        (query_handler, Rename, "@command"),
        (event_handler, Rename, "@command"),
        (command_handler, Renamed, "@event"),
    ],
)
def test_a_kind_handler_rejects_messages_of_other_kinds(
    decorate: Any, message: type, wrong: str
) -> None:
    async def handle(message: Any) -> str:
        return ""

    source = decorate(handle)
    with pytest.raises(
        RuleViolation, match=f"handles only @.* messages, but .*{message.__qualname__} is a {wrong}"
    ) as exc:
        Mediator().register(message, source)
    assert exc.value.handler is source


def test_scan_reports_kind_mismatches_with_the_other_problems(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "app.py": """
                from mediary.cqrs import Command, Query, command, command_handler, query

                @query
                class Load(Query[str]):
                    pass

                @command
                class Save(Command[None]):
                    pass

                @command_handler
                async def load(query: Load) -> str: ...

                @command_handler
                class SaveHandler:
                    async def handle(self, command: Save) -> None: ...
            """
        }
    )
    m = Mediator()
    with pytest.raises(ScanError) as exc:
        m.scan(pkg)
    (problem,) = exc.value.errors
    assert isinstance(problem, RuleViolation)
    assert "Load is a @query" in str(problem)


def test_a_query_handler_still_must_return_something() -> None:
    @query_handler
    async def nothing(query: GetName) -> None:
        pass

    with pytest.raises(RuleViolation, match="a query handler must return what it read"):
        Mediator().register(GetName, nothing)


async def test_kind_behaviors_wrap_only_their_kind(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "behaviors.py": """
                from mediary.cqrs import command_behavior, event_behavior, query_behavior

                log = []

                @command_behavior
                async def commands(message, next):
                    log.append(f"command {type(message).__name__}")
                    return await next()

                @query_behavior(order=5)
                class Queries:
                    async def handle(self, message, next):
                        log.append(f"query {type(message).__name__}")
                        return await next()

                @event_behavior
                async def events(message, next):
                    log.append(f"event {type(message).__name__}")
                    return await next()
            """
        }
    )
    m = make_mediator()
    m.scan(pkg)
    await m.send(Rename(1, "ada"))
    await m.send(GetName(1))
    log = __import__(f"{pkg}.behaviors", fromlist=["log"]).log
    assert log == ["command Rename", "event Renamed", "query GetName"]


def test_kind_decorators_have_their_own_names_and_docs() -> None:
    for decorate in (command_handler, query_handler, event_handler):
        assert decorate.__module__ == "mediary.cqrs"
        assert decorate.__doc__ is not None
        assert "@handler" in decorate.__doc__
    assert getattr(command_behavior, "__name__", None) == "command_behavior"
    assert event_behavior.__doc__ is not None
    assert 'kinds={"event"}' in event_behavior.__doc__
