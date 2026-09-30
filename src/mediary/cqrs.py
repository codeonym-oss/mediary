"""CQRS: commands change state, queries read it, and events announce what happened.

``@command`` and ``@query`` are sent to exactly one handler; ``@event`` is published to any number.
A query handler annotated to return None is rejected when it is registered or scanned.
``@stream_query`` is a query whose one handler yields its results, for reads too big to return at
once: it is streamed with ``Mediator.stream``.

``@command_handler``, ``@query_handler``, ``@stream_query_handler`` and ``@event_handler`` are
``@handler`` for one kind: a handler they mark is rejected if its message is of another kind.
``@command_behavior`` and its counterparts are ``@behavior(kinds={"command"})`` and so on.
``CommandHandler``, ``QueryHandler``, ``StreamQueryHandler`` and ``EventHandler`` let a handler
class declare what it handles. The ``Command``, ``Query``, ``StreamQuery`` and ``Event`` bases are
optional; they type the narrow senders ``CommandSender``, ``QuerySender``, ``StreamQuerySender``
and ``EventPublisher``.

The pack is built only on the public ``mediary.kinds`` API. Give each piece of code the
narrowest sender it needs, so that, for instance, a read-only view can't send a command.

Example:
    .. code-block:: python

        @query
        @dataclass
        class GetUser(Query[User]):
            user_id: int

        @query_handler
        async def get_user(query: GetUser, users: UserRepository) -> User: ...

        async def show(users: QuerySender, user_id: int) -> User:
            return await users.send(GetUser(user_id))

        await show(mediator, 1)  # a Mediator is each of the narrow senders

"""

from typing import Any, Protocol, TypeAlias, TypeVar

from ._handlers import Handler, StreamHandler
from ._markers import Returns, Yields
from ._streaming import Stream
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
    "Event",
    "EventHandler",
    "EventPublisher",
    "Query",
    "QueryHandler",
    "QuerySender",
    "StreamQuery",
    "StreamQueryHandler",
    "StreamQuerySender",
    "command",
    "command_behavior",
    "command_handler",
    "event",
    "event_behavior",
    "event_handler",
    "query",
    "query_behavior",
    "query_handler",
    "stream_query",
    "stream_query_behavior",
    "stream_query_handler",
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


class StreamQuery(Yields[_R_co]):
    """Base for stream queries: declares what the handler yields, and types ``Mediator.stream``.

    Example:
        .. code-block:: python

            @stream_query
            @dataclass
            class ExportUsers(StreamQuery[User]):
                since: date

    """

    __slots__ = ()


class Event:
    """Base for events: types ``EventPublisher.publish``. It takes no type: events return nothing.

    Example:
        .. code-block:: python

            @event
            @dataclass
            class UserRenamed(Event):
                user_id: int
                name: str

    """

    __slots__ = ()


def _returns_a_result(info: HandlerInfo) -> str | None:
    if info.returns is type(None):
        return "a query handler must return what it read, but it is annotated to return None"
    return None


_COMMAND = define_kind("command", dispatch="send")
_QUERY = define_kind("query", dispatch="send", rules=[_returns_a_result])
_STREAM_QUERY = define_kind("stream_query", dispatch="stream")
_EVENT = define_kind("event", dispatch="publish")


_BASES: dict[type, str] = {
    Command: "command",
    Query: "query",
    StreamQuery: "stream_query",
    Event: "event",
}


def _check_base(cls: type, own: type) -> None:
    """Raise ``TypeError`` if ``cls`` subclasses the base of a kind other than ``own``'s."""
    for base, name in _BASES.items():
        if base is not own and issubclass(cls, base):
            raise TypeError(
                f"{cls.__qualname__} subclasses {base.__name__}, so decorate it with @{name}"
            )


def command(cls: _C) -> _C:
    """Mark a class as a command: a request to change state, sent to exactly one handler.

    Raises:
        TypeError: ``cls`` subclasses ``Query``, ``StreamQuery`` or ``Event``.

    """
    _check_base(cls, Command)
    return _COMMAND(cls)


def query(cls: _C) -> _C:
    """Mark a class as a query: a request to read state, sent to exactly one handler.

    Its handler must not be annotated to return None.

    Raises:
        TypeError: ``cls`` subclasses ``Command``, ``StreamQuery`` or ``Event``.

    """
    _check_base(cls, Query)
    return _QUERY(cls)


def stream_query(cls: _C) -> _C:
    """Mark a class as a stream query: a read whose one handler yields its results.

    It is streamed with ``Mediator.stream``, and its handler is an async generator, as for a
    ``@stream_request``.

    Raises:
        TypeError: ``cls`` subclasses ``Command``, ``Query`` or ``Event``.

    """
    _check_base(cls, StreamQuery)
    return _STREAM_QUERY(cls)


def event(cls: _C) -> _C:
    """Mark a class as an event: something that happened, published to all of its handlers.

    Raises:
        TypeError: ``cls`` subclasses ``Command``, ``Query`` or ``StreamQuery``.

    """
    _check_base(cls, Event)
    return _EVENT(cls)


_Command = TypeVar("_Command", bound=Command[Any])
_Query = TypeVar("_Query", bound=Query[Any])
_StreamQuery = TypeVar("_StreamQuery", bound=StreamQuery[Any])
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

StreamQueryHandler: TypeAlias = StreamHandler[_StreamQuery, _R]
"""The shape of a class handler of a stream query: ``StreamHandler`` bound to ``StreamQuery``."""

EventHandler: TypeAlias = Handler[_Event, None]
"""The shape of a class handler of an event: ``Handler`` of the event, returning None."""


def _named(decorator: _D, name: str, doc: str) -> _D:
    """Give ``decorator`` a name and docstring of its own, for help() and the API reference."""
    names = {"__name__": name, "__qualname__": name, "__module__": __name__, "__doc__": doc}
    for attr, value in names.items():
        setattr(decorator, attr, value)
    return decorator


def _plural(label: str) -> str:
    return f"{label[:-1]}ies" if label.endswith("y") else f"{label}s"


def _handler_doc(kind: str) -> str:
    label = kind.replace("_", " ")
    article, labels = ("an" if label[0] in "aeiou" else "a"), _plural(label)
    return f"""Mark {article} {label} handler: like ``@handler``, for handlers of {labels} only.

It takes the same arguments as ``@handler``. Registering or scanning the handler for a message
that isn't {article} {label} raises ``RuleViolation``, which names the handler and the message.
"""


def _behavior_doc(kind: str) -> str:
    label = kind.replace("_", " ")
    return f"""Mark a behavior that wraps only {_plural(label)}: ``@behavior(kinds={{"{kind}"}})``.

It takes the same ``order`` as ``@behavior``.
"""


command_handler: HandlerDecorator = _named(
    handler_for(_COMMAND), "command_handler", _handler_doc("command")
)
query_handler: HandlerDecorator = _named(
    handler_for(_QUERY), "query_handler", _handler_doc("query")
)
stream_query_handler: HandlerDecorator = _named(
    handler_for(_STREAM_QUERY), "stream_query_handler", _handler_doc("stream_query")
)
event_handler: HandlerDecorator = _named(
    handler_for(_EVENT), "event_handler", _handler_doc("event")
)
command_behavior: BehaviorDecorator = _named(
    behavior_for(_COMMAND), "command_behavior", _behavior_doc("command")
)
query_behavior: BehaviorDecorator = _named(
    behavior_for(_QUERY), "query_behavior", _behavior_doc("query")
)
stream_query_behavior: BehaviorDecorator = _named(
    behavior_for(_STREAM_QUERY), "stream_query_behavior", _behavior_doc("stream_query")
)
event_behavior: BehaviorDecorator = _named(
    behavior_for(_EVENT), "event_behavior", _behavior_doc("event")
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


class StreamQuerySender(Protocol):
    """Something that streams stream queries, such as a ``Mediator``.

    It is apart from ``QuerySender``, so that implementing one doesn't require the other.
    """

    def stream(self, query: StreamQuery[_R], /) -> Stream[_R]:
        """Stream the items ``query``'s handler yields."""
        ...


class EventPublisher(Protocol):
    """Something that publishes events, such as a ``Mediator``.

    Only events that subclass ``Event`` type-check: a command or a query can't be published
    through it.
    """

    async def publish(self, event: Event, /) -> None:
        """Publish ``event`` to all of its handlers."""
        ...
