"""CQRS: commands change state, queries read it, and events announce what happened.

`@command` and `@query` are sent to exactly one handler; `@event` is published to any number.
A query handler annotated to return None is rejected when it is registered or scanned.
Behaviors can target each with `kinds={"command"}`, `{"query"}` or `{"event"}`.

The pack is built only on the public `mediary.kinds` API. Give each piece of code the
narrowest sender it needs, so that, for instance, a read-only view can't send a command.

Example:
    ```python
    @query
    @dataclass
    class GetUser(Query[User]):
        user_id: int

    async def show(users: QuerySender, user_id: int) -> User:
        return await users.send(GetUser(user_id))

    await show(mediator, 1)  # a Mediator is both a QuerySender and a CommandSender
    ```

"""

from typing import Protocol, TypeVar

from ._markers import Returns
from .kinds import HandlerInfo, define_kind

__all__ = ["Command", "CommandSender", "Query", "QuerySender", "command", "event", "query"]

_R = TypeVar("_R")
_R_co = TypeVar("_R_co", covariant=True)
_C = TypeVar("_C", bound=type)


class Command(Returns[_R_co]):
    """Base for commands: declares what the handler returns, and types `CommandSender.send`."""

    __slots__ = ()


class Query(Returns[_R_co]):
    """Base for queries: declares what the handler returns, and types `QuerySender.send`."""

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
        TypeError: `cls` subclasses `Query`.

    """
    if issubclass(cls, Query):
        raise TypeError(f"{cls.__qualname__} subclasses Query, so decorate it with @query")
    return _COMMAND(cls)


def query(cls: _C) -> _C:
    """Mark a class as a query: a request to read state, sent to exactly one handler.

    Its handler must not be annotated to return None.

    Raises:
        TypeError: `cls` subclasses `Command`.

    """
    if issubclass(cls, Command):
        raise TypeError(f"{cls.__qualname__} subclasses Command, so decorate it with @command")
    return _QUERY(cls)


def event(cls: _C) -> _C:
    """Mark a class as an event: something that happened, published to all of its handlers."""
    return _EVENT(cls)


class CommandSender(Protocol):
    """Something that sends commands, such as a `Mediator`."""

    async def send(self, command: Command[_R], /) -> _R:
        """Send `command` to its handler and return the result."""
        ...


class QuerySender(Protocol):
    """Something that sends queries, such as a `Mediator`."""

    async def send(self, query: Query[_R], /) -> _R:
        """Send `query` to its handler and return the result."""
        ...
