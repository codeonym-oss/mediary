"""Handlers: their structural shape, the `@handler` decorator, and binding one to its request."""

import inspect
import typing
from collections.abc import Callable
from typing import Any, Protocol, TypeVar, overload

from ._errors import InvalidHandlerSignature
from ._markers import Marker, mark, marker_of

_Req_contra = TypeVar("_Req_contra", contravariant=True)
_Res_co = TypeVar("_Res_co", covariant=True)


class Handler(Protocol[_Req_contra, _Res_co]):
    """The shape of a request handler: any class with an async `handle` taking the request.

    No base class is needed; type checkers match handlers structurally.

    Example:
        class GetUserHandler:
            async def handle(self, request: GetUser) -> User: ...

    """

    async def handle(self, request: _Req_contra, /) -> _Res_co:
        """Handle `request` and return its result."""
        ...


_H = TypeVar("_H", bound=Handler[Any, Any])


# A handler class is also a `type`, so the overloads overlap by design: bare use (a class with
# `handle`) matches first, and anything else names the request.
@overload
def handler(cls: type[_H], /) -> type[_H]: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def handler(request_type: type[object], /) -> Callable[[type[_H]], type[_H]]: ...
def handler(target: type, /) -> Any:
    """Mark a class as a handler, so `Mediator.scan` finds and registers it.

    Used bare, the handler serves the request named by the type hint of `handle`'s request
    parameter. Given a request type, it serves that request whatever the hint says.

    Example:
        @handler
        class GetUserHandler:
            async def handle(self, request: GetUser) -> User: ...

        @handler(GetUser)
        class LegacyGetUserHandler:
            async def handle(self, request) -> User: ...

    """
    if hasattr(target, "handle"):
        return mark(target, Marker(kind="handler"))

    def decorate(cls: type[_H]) -> type[_H]:
        return mark(cls, Marker(kind="handler", target=target))

    return decorate


def is_handler(cls: type) -> bool:
    """Whether `cls` itself is decorated with `@handler`."""
    marker = marker_of(cls)
    return marker is not None and marker.kind == "handler"


def check_handle(cls: type) -> Callable[..., Any]:
    """Return `cls.handle`, or raise if it isn't an async method."""
    handle = getattr(cls, "handle", None)
    if not inspect.iscoroutinefunction(handle):
        raise InvalidHandlerSignature(cls, "it needs an `async def handle(self, request)`")
    return handle


def bound_request(cls: type) -> type:
    """Return the request type a `@handler` class serves.

    That is the type given to `@handler(...)`, else the resolved type hint of the first
    parameter of `handle` after `self`. Forward references and deferred annotations resolve
    against the handler's module.

    Raises:
        InvalidHandlerSignature: there is no async `handle`, or its request hint is missing,
            unresolvable or not a single class.

    """
    marker = marker_of(cls)
    if marker is not None and marker.target is not None:
        return marker.target
    handle = check_handle(cls)
    params = list(inspect.signature(handle).parameters.values())[1:]
    if not params:
        raise InvalidHandlerSignature(cls, "`handle` takes no request parameter")
    name = params[0].name
    try:
        hints = typing.get_type_hints(handle)
    except Exception as exc:
        raise InvalidHandlerSignature(
            cls, f"cannot resolve the type hints of `handle` ({type(exc).__name__}: {exc})"
        ) from exc
    hint = hints.get(name)
    if hint is None:
        raise InvalidHandlerSignature(
            cls,
            f"the request parameter `{name}` has no type hint; annotate it, or name the request "
            "with @handler(SomeRequest)",
        )
    if not isinstance(hint, type):
        raise InvalidHandlerSignature(
            cls, f"the request parameter `{name}` must be hinted with one class, not {hint!r}"
        )
    return hint
