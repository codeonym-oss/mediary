"""Markers the decorators attach to user classes, and the `Returns` typing marker."""

from dataclasses import dataclass
from typing import Final, Generic, Literal, TypeVar

_R_co = TypeVar("_R_co", covariant=True)
_C = TypeVar("_C", bound=type)
_T = TypeVar("_T")

Lifetime = Literal["transient", "singleton"]

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


def request(cls: _C) -> _C:
    """Mark a class as a request that `Mediator.send` dispatches to exactly one handler.

    The class is returned unchanged apart from the marker; it can be a dataclass, a pydantic
    model or any plain class. Subclasses are not requests unless they are decorated too.
    """
    return mark(cls, Marker(kind="request"))


def mark(obj: _T, marker: Marker) -> _T:
    """Attach `marker` to a class or function and return it."""
    setattr(obj, _MARKER_ATTR, marker)
    return obj


def marker_of(obj: object) -> Marker | None:
    """Return the marker decorated onto `obj` itself (never one inherited by a class)."""
    marker = getattr(obj, "__dict__", {}).get(_MARKER_ATTR)
    return marker if isinstance(marker, Marker) else None


def is_request(cls: type) -> bool:
    """Whether `cls` itself is decorated as a request."""
    marker = marker_of(cls)
    return marker is not None and marker.kind == "request"
