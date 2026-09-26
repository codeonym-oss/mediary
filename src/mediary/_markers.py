"""Markers the decorators attach, the kinds of message, and the `Returns`/`Yields` markers."""

import inspect
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Final, Generic, Literal, TypeVar, get_args

_R_co = TypeVar("_R_co", covariant=True)
_C = TypeVar("_C", bound=type)
_T = TypeVar("_T")

Lifetime = Literal["transient", "singleton"]
Dispatch = Literal["send", "publish", "stream"]

_MARKER_ATTR: Final = "__mediary_marker__"


class Returns(Generic[_R_co]):
    """Declare what a request's handler returns, so `Mediator.send` is typed.

    It only informs type checkers: it has no behaviour and no runtime cost. Requests that don't
    inherit it still work, and `send` returns `Any` for them.

    Example:
        @request
        @dataclass
        class GetUser(Returns[User]):
            user_id: int

        user = await mediator.send(GetUser(1))  # typed as User

    """

    __slots__ = ()


class Yields(Generic[_R_co]):
    """Declare what a stream request's handler yields, so `Mediator.stream` is typed.

    Like `Returns`, it only informs type checkers. Stream requests that don't inherit it still
    work, and `stream` yields `Any` for them.

    Example:
        @stream_request
        @dataclass
        class ExportOrders(Yields[Order]):
            since: date

        async with mediator.stream(ExportOrders(today)) as orders:
            async for order in orders:  # typed as Order
                ...

    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Marker:
    """What a decorator recorded about a class or function.

    `target` is the request type an `@handler(SomeRequest)` names explicitly, and `lifetime`
    how long a class handler's instance lives. `order` and `kinds` are a behavior's place in
    the pipeline and the request kinds it wraps (None for all).
    """

    kind: str
    target: type | None = None
    lifetime: Lifetime = "transient"
    order: int = 0
    kinds: frozenset[str] | None = None


def mark(obj: _T, marker: Marker) -> _T:
    """Attach `marker` to a class or function and return it."""
    setattr(obj, _MARKER_ATTR, marker)
    return obj


def marker_of(obj: object) -> Marker | None:
    """Return the marker decorated onto `obj` itself (never one inherited by a class)."""
    marker = getattr(obj, "__dict__", {}).get(_MARKER_ATTR)
    return marker if isinstance(marker, Marker) else None


@dataclass(frozen=True, slots=True)
class HandlerInfo:
    """What a kind's rules are told about a handler being registered for one of its messages.

    `returns` is the handler's resolved return hint (`type(None)` for `-> None`), or
    `inspect.Signature.empty` when it has none.
    """

    message_type: type
    handler: Any
    returns: Any = inspect.Signature.empty


HandlerRule = Callable[[HandlerInfo], str | None]
"""Checks a handler of a kind: returns why it can't be registered, or None if it can."""


@dataclass(frozen=True, slots=True, eq=False)
class Kind:
    """A kind of message, such as "request". Calling it decorates a class as that kind.

    Create kinds with `define_kind`.
    """

    name: str
    dispatch: Dispatch
    rules: tuple[HandlerRule, ...] = ()

    def __call__(self, cls: _C, /) -> _C:
        """Mark `cls` as a message of this kind and return it unchanged."""
        return mark(cls, Marker(kind=self.name))

    def check(self, info: HandlerInfo) -> str | None:
        """Return why the handler `info` describes breaks a rule of this kind, or None."""
        for rule in self.rules:
            reason = rule(info)
            if reason is not None:
                return reason
        return None


_RESERVED: Final = frozenset({"handler", "behavior"})
_KINDS: dict[str, Kind] = {}


def define_kind(name: str, *, dispatch: Dispatch, rules: Iterable[HandlerRule] = ()) -> Kind:
    """Define a new kind of message; the returned `Kind` is its class decorator.

    Messages of a `dispatch="send"` kind have exactly one handler and go through
    `Mediator.send`; those of a `dispatch="publish"` kind have any number and go through
    `Mediator.publish`; those of a `dispatch="stream"` kind have exactly one async generator
    handler and go through `Mediator.stream`. Every handler registered or scanned for a
    message of the kind must pass each of `rules`. Behaviors target the kind by name, with
    `kinds={name}`.

    Kinds are global, like the classes they decorate, so define each one once, at import time.

    Example:
        def must_return(info: HandlerInfo) -> str | None:
            if info.returns is type(None):
                return "it must return a result"
            return None

        lookup = define_kind("lookup", dispatch="send", rules=[must_return])

        @lookup
        class FindUser(Returns[User]): ...

    Raises:
        ValueError: `name` is already defined or reserved, or `dispatch` is unknown.

    """
    if name in _KINDS or name in _RESERVED:
        raise ValueError(f"a kind named {name!r} is already defined")
    if dispatch not in get_args(Dispatch):
        raise ValueError(f'dispatch must be "send", "publish" or "stream", not {dispatch!r}')
    kind = _KINDS[name] = Kind(name, dispatch, tuple(rules))
    return kind


def kind_of(cls: type) -> Kind | None:
    """Return the kind `cls` itself is decorated as, or None if it isn't a message."""
    marker = marker_of(cls)
    return _KINDS.get(marker.kind) if marker is not None else None


_REQUEST = define_kind("request", dispatch="send")
_NOTIFICATION = define_kind("notification", dispatch="publish")
_STREAM_REQUEST = define_kind("stream_request", dispatch="stream")


def request(cls: _C) -> _C:
    """Mark a class as a request that `Mediator.send` dispatches to exactly one handler.

    The class is returned unchanged apart from the marker; it can be a dataclass, a pydantic
    model or any plain class. Subclasses are not requests unless they are decorated too.
    """
    return _REQUEST(cls)


def notification(cls: _C) -> _C:
    """Mark a class as a notification that `Mediator.publish` sends to all of its handlers.

    A notification has zero or more handlers, written like request handlers. Subclasses are
    not notifications unless they are decorated too.
    """
    return _NOTIFICATION(cls)


def stream_request(cls: _C) -> _C:
    """Mark a class as a request that `Mediator.stream` dispatches to one async generator handler.

    Its handler yields any number of items, which the caller consumes with `async for` as they
    are produced. Subclasses are not stream requests unless they are decorated too.
    """
    return _STREAM_REQUEST(cls)


def is_notification(cls: type) -> bool:
    """Whether `cls` itself is decorated as a kind of message that is published."""
    kind = kind_of(cls)
    return kind is not None and kind.dispatch == "publish"
