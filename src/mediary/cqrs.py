"""CQRS: commands change state, queries read it, and events announce what happened.

``@command`` and ``@query`` are sent to exactly one handler; ``@event`` is published to any number.
A query handler annotated to return None is rejected when it is registered or scanned.

``@command_handler``, ``@query_handler`` and ``@event_handler`` are ``@handler`` for one kind:
a handler they mark is rejected if its message is of another kind. ``@command_behavior``,
``@query_behavior`` and ``@event_behavior`` are ``@behavior(kinds={"command"})`` and its
counterparts. ``CommandHandler``, ``QueryHandler`` and ``EventHandler`` let a handler class
declare what it handles.

The pack is built only on the public ``mediary.kinds`` API. Give each piece of code the
narrowest sender it needs, so that, for instance, a read-only view can't send a command.

Example:
    .. code-block:: python

        @query
        @dataclass
        class GetUser(Query[User]):
            user_id: int

        async def show(users: QuerySender, user_id: int) -> User:
            return await users.send(GetUser(user_id))

        @query_handler
        async def get_user(query: GetUser, users: UserRepository) -> User: ...

        async def show(users: QuerySender, user_id: int) -> User:
            return await users.send(GetUser(user_id))

        await show(mediator, 1)  # a Mediator is both a QuerySender and a CommandSender

"""

from typing import Any, Protocol, TypeAlias, TypeVar

from ._handlers import Handler
from ._markers import Returns
from .kinds import (
    BehaviorDecorator,
    HandlerDecorator,
    HandlerInfo,
    behavior_for,
    define_kind,
    handler_for,
)

__all__ = [
    "Command",
    "CommandHandler",
    "CommandSender",
    "EventHandler",
    "Query",
    "QueryHandler",
    "QuerySender",
    "command",
    "command_behavior",
    "command_handler",
    "event",
    "event_behavior",
    "event_handler",
    "query",
    "query_behavior",
    "query_handler",
]

_R = TypeVar("_R")
_R_co = TypeVar("_R_co", covariant=True)
_C = TypeVar("_C", bound=type)
_D = TypeVar("_D")


class Command(Returns[_R_co]):
    """Base for commands: declares what the handler returns, and types ``CommandSender.send``."""

    __slots__ = ()


class Query(Returns[_R_co]):
    """Base for queries: declares what the handler returns, and types ``QuerySender.send``."""

    __slots__ = ()


def _returns_a_result(info: HandlerInfo) -> str | None:
    if info.returns is type(None):
        return "a query handler must return what it read, but it is annotated to return None"
    return None


_COMMAND = define_kind("command", dispatch="send")
_QUERY = define_kind("query", dispatch="send", rules=[_returns_a_result])
_EVENT = define_kind("event", dispatch="publish")


def command(cls: _C) -> _C:
    """Mark a class as a command: a request to change state, sent to exactly one handler.

    Raises:
        TypeError: ``cls`` subclasses ``Query``.

    """
    if issubclass(cls, Query):
        raise TypeError(f"{cls.__qualname__} subclasses Query, so decorate it with @query")
    return _COMMAND(cls)


def query(cls: _C) -> _C:
    """Mark a class as a query: a request to read state, sent to exactly one handler.

    Its handler must not be annotated to return None.

    Raises:
        TypeError: ``cls`` subclasses ``Command``.

    """
    if issubclass(cls, Command):
        raise TypeError(f"{cls.__qualname__} subclasses Command, so decorate it with @command")
    return _QUERY(cls)


def event(cls: _C) -> _C:
    """Mark a class as an event: something that happened, published to all of its handlers."""
    return _EVENT(cls)


_Command = TypeVar("_Command", bound=Command[Any])
_Query = TypeVar("_Query", bound=Query[Any])
_Event = TypeVar("_Event")

CommandHandler: TypeAlias = Handler[_Command, _R]
"""The shape of a class handler of a command: ``Handler`` with the message bound to ``Command``.

Example:
    .. code-block:: python

        @command_handler
        class RenameUserHandler(CommandHandler[RenameUser, None]):
            async def handle(self, command: RenameUser) -> None: ...

"""

QueryHandler: TypeAlias = Handler[_Query, _R]
"""The shape of a class handler of a query: ``Handler`` with the message bound to ``Query``."""

EventHandler: TypeAlias = Handler[_Event, None]
"""The shape of a class handler of an event: ``Handler`` of the event, returning None."""


def _named(decorator: _D, name: str, doc: str) -> _D:
    """Give ``decorator`` a name and docstring of its own, for help() and the API reference."""
    names = {"__name__": name, "__qualname__": name, "__module__": __name__, "__doc__": doc}
    for attr, value in names.items():
        setattr(decorator, attr, value)
    return decorator


_HANDLER_DOC = """Mark a {kind} handler: like ``@handler``, for handlers of {kind}s only.

It takes the same arguments as ``@handler``. Registering or scanning the handler for a message
that isn't {article} {kind} raises ``RuleViolation``, which names the handler and the message.
"""

_BEHAVIOR_DOC = """Mark a behavior that wraps only {kind}s: ``@behavior(kinds={{"{kind}"}})``.

It takes the same ``order`` as ``@behavior``.
"""

command_handler: HandlerDecorator = _named(
    handler_for(_COMMAND), "command_handler", _HANDLER_DOC.format(kind="command", article="a")
)
query_handler: HandlerDecorator = _named(
    handler_for(_QUERY), "query_handler", _HANDLER_DOC.format(kind="query", article="a")
)
event_handler: HandlerDecorator = _named(
    handler_for(_EVENT), "event_handler", _HANDLER_DOC.format(kind="event", article="an")
)
command_behavior: BehaviorDecorator = _named(
    behavior_for(_COMMAND), "command_behavior", _BEHAVIOR_DOC.format(kind="command")
)
query_behavior: BehaviorDecorator = _named(
    behavior_for(_QUERY), "query_behavior", _BEHAVIOR_DOC.format(kind="query")
)
event_behavior: BehaviorDecorator = _named(
    behavior_for(_EVENT), "event_behavior", _BEHAVIOR_DOC.format(kind="event")
)


class CommandSender(Protocol):
    """Something that sends commands, such as a ``Mediator``."""

    async def send(self, command: Command[_R], /) -> _R:
        """Send ``command`` to its handler and return the result."""
        ...


class QuerySender(Protocol):
    """Something that sends queries, such as a ``Mediator``."""

    async def send(self, query: Query[_R], /) -> _R:
        """Send ``query`` to its handler and return the result."""
        ...
