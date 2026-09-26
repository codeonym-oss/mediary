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
    """What a decorator recorded about a class."""

    kind: str


def request(cls: _C) -> _C:
    """Mark a class as a request that `Mediator.send` dispatches to exactly one handler.

    The class is returned unchanged apart from the marker; it can be a dataclass, a pydantic
    model or any plain class. Subclasses are not requests unless they are decorated too.
    """
    setattr(cls, _MARKER_ATTR, Marker(kind="request"))
    return cls


def marker_of(cls: type) -> Marker | None:
    """Return the marker decorated onto `cls` itself (never an inherited one)."""
    marker = cls.__dict__.get(_MARKER_ATTR)
    return marker if isinstance(marker, Marker) else None
