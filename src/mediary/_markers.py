"""Markers the decorators attach to user classes, and the `Returns` typing marker."""

from dataclasses import dataclass
from typing import Final, Generic, TypeVar

_R_co = TypeVar("_R_co", covariant=True)
_C = TypeVar("_C", bound=type)

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
    """What a decorator recorded about a class.

    `target` is the request type an `@handler(SomeRequest)` names explicitly.
    """

    kind: str
    target: type | None = None


def request(cls: _C) -> _C:
    """Mark a class as a request that `Mediator.send` dispatches to exactly one handler.

    The class is returned unchanged apart from the marker; it can be a dataclass, a pydantic
    model or any plain class. Subclasses are not requests unless they are decorated too.
    """
    return mark(cls, Marker(kind="request"))


def mark(cls: _C, marker: Marker) -> _C:
    """Attach `marker` to `cls` and return `cls`."""
    setattr(cls, _MARKER_ATTR, marker)
    return cls


def marker_of(cls: type) -> Marker | None:
    """Return the marker decorated onto `cls` itself (never an inherited one)."""
    marker = cls.__dict__.get(_MARKER_ATTR)
    return marker if isinstance(marker, Marker) else None


def is_request(cls: type) -> bool:
    """Whether `cls` itself is decorated as a request."""
    marker = marker_of(cls)
    return marker is not None and marker.kind == "request"
