"""Handlers: their shape, the `@handler` decorator, and binding one to its request."""

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, get_args, overload

from ._errors import InvalidHandlerSignature
from ._markers import Lifetime, Marker, mark, marker_of
from ._resolving import Resolver, Shape, require_async, resolve, shape

_Req_contra = TypeVar("_Req_contra", contravariant=True)
_Res_co = TypeVar("_Res_co", covariant=True)

_LIFETIMES = get_args(Lifetime)


class Handler(Protocol[_Req_contra, _Res_co]):
    """The shape of a class handler: any class with an async `handle` taking the request.

    No base class is needed; type checkers match handlers structurally.

    Example:
        class GetUserHandler:
            async def handle(self, request: GetUser) -> User: ...

    """

    async def handle(self, request: _Req_contra, /) -> _Res_co:
        """Handle `request` and return its result."""
        ...


_Handles = TypeVar("_Handles", bound=Handler[Any, Any])
_Fn = TypeVar("_Fn", bound=Callable[..., Awaitable[Any]])
_Any = TypeVar("_Any", bound=type[Handler[Any, Any]] | Callable[..., Awaitable[Any]])


# A handler class is also a `type`, so the overloads overlap by design: bare use (a class with
# `handle`, or a function) matches first, and anything else names the request.
@overload
def handler(target: type[_Handles], /) -> type[_Handles]: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def handler(target: _Fn, /) -> _Fn: ...
@overload
def handler(
    request_type: type[object] | None = None, /, *, lifetime: Lifetime = "transient"
) -> Callable[[_Any], _Any]: ...
def handler(target: Any = None, /, *, lifetime: Lifetime = "transient") -> Any:
    """Mark a class or async function as a handler, so `Mediator.scan` finds and registers it.

    Used bare, the handler serves the request named by the type hint of its request parameter:
    the first parameter of a function, or of a class's `handle` after `self`. Given a request
    type, it serves that request whatever the hint says.

    A class handler is resolved through the mediator's `Resolver` for every send, or only once
    with `lifetime="singleton"`. A function handler's parameters after the request are resolved
    through the `Resolver` by their type hints on every send.

    Example:
        @handler
        class GetUserHandler:
            async def handle(self, request: GetUser) -> User: ...

        @handler(lifetime="singleton")
        class CachedGetUserHandler: ...

        @handler
        async def delete_user(request: DeleteUser, repo: UserRepository) -> None: ...

    Raises:
        ValueError: `lifetime` is not "transient" or "singleton".

    """
    if lifetime not in _LIFETIMES:
        raise ValueError(f"lifetime must be one of {_LIFETIMES}, not {lifetime!r}")
    if inspect.isfunction(target) or hasattr(target, "handle"):
        return mark(target, Marker(kind="handler", lifetime=lifetime))

    def decorate(obj: _Any) -> _Any:
        return mark(obj, Marker(kind="handler", target=target, lifetime=lifetime))

    return decorate


Invoke = Callable[[Any, Resolver], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Binding:
    """A handler bound to its request type, with how to call it for a request."""

    request_type: type
    source: Any
    invoke: Invoke


def bind(source: Any, request_type: type | None = None) -> Binding:
    """Bind a handler class or function to the request it serves.

    The request type is `request_type`, else the one given to `@handler(...)`, else the type
    hint of the request parameter. Forward references and deferred annotations resolve against
    the handler's module.

    Raises:
        InvalidHandlerSignature: the handler isn't an async function or a class with an async
            `handle`, or a hint it needs is missing, unresolvable or (for the request) not a
            single class.

    """
    marker = marker_of(source)
    if request_type is None and marker is not None:
        request_type = marker.target
    lifetime = marker.lifetime if marker is not None else "transient"
    if isinstance(source, type):
        handle = require_async(
            source,
            getattr(source, "handle", None),
            "an `async def handle(self, request)`",
            InvalidHandlerSignature,
        )
        params = shape(
            source, handle, leading=("request",), method=True, error=InvalidHandlerSignature
        )
        invoke = _class_invoker(source, lifetime)
    else:
        function = require_async(
            source, source, "to be an `async def` function or a class", InvalidHandlerSignature
        )
        if lifetime != "transient":
            raise InvalidHandlerSignature(source, "only class handlers have a lifetime")
        params = shape(
            source, function, leading=("request",), method=False, error=InvalidHandlerSignature
        )
        invoke = _function_invoker(function, params)
    if request_type is None:
        request_type = _request_hint(source, params)
    return Binding(request_type, source, invoke)


def _request_hint(source: Any, params: Shape) -> type:
    hint = params.hint(0)
    name = params.leading[0].name
    if hint is None:
        raise InvalidHandlerSignature(
            source,
            f"the request parameter `{name}` has no type hint; annotate it, or name the request "
            "with @handler(SomeRequest)",
        )
    if not isinstance(hint, type):
        raise InvalidHandlerSignature(
            source, f"the request parameter `{name}` must be hinted with one class, not {hint!r}"
        )
    return hint


def _class_invoker(cls: type, lifetime: Lifetime) -> Invoke:
    if lifetime == "transient":

        async def invoke(request: Any, resolver: Resolver) -> Any:
            return await (await resolve(resolver, cls)).handle(request)

        return invoke

    instances: list[Any] = []

    async def invoke_singleton(request: Any, resolver: Resolver) -> Any:
        if not instances:
            instance = await resolve(resolver, cls)
            if not instances:  # another send may have resolved it while this one awaited
                instances.append(instance)
        return await instances[0].handle(request)

    return invoke_singleton


def _function_invoker(fn: Callable[..., Awaitable[Any]], params: Shape) -> Invoke:
    async def invoke(request: Any, resolver: Resolver) -> Any:
        args, kwargs = await params.dependencies(resolver)
        return await fn(request, *args, **kwargs)

    return invoke
