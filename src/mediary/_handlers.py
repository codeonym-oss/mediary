"""Handlers: their shape, the ``@handler`` decorator, and binding one to its request."""

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, get_args, overload

from ._errors import InvalidHandlerSignature
from ._markers import Lifetime, Marker, mark, marker_of
from ._resolving import Resolver, Shape, require_async, resolve, shape

_Req_contra = TypeVar("_Req_contra", contravariant=True)
_Res_co = TypeVar("_Res_co", covariant=True)

_LIFETIMES = get_args(Lifetime)


class Handler(Protocol[_Req_contra, _Res_co]):
    """The shape of a class handler: any class with an async ``handle`` taking the request.

    No base class is needed; type checkers match handlers structurally.

    Example:
        .. code-block:: python

            class GetUserHandler:
                async def handle(self, request: GetUser) -> User: ...

    """

    async def handle(self, request: _Req_contra, /) -> _Res_co:
        """Handle ``request`` and return its result."""
        ...


class StreamHandler(Protocol[_Req_contra, _Res_co]):
    """The shape of a class handler for a stream request: ``handle`` is an async generator.

    Example:
        .. code-block:: python

            class ExportOrdersHandler:
                async def handle(self, request: ExportOrders) -> AsyncIterator[Order]:
                    async for order in self.repo.since(request.since):
                        yield order

    """

    def handle(self, request: _Req_contra, /) -> AsyncIterator[_Res_co]:
        """Yield the items of ``request``."""
        ...


_HandlerFn = Callable[..., Awaitable[Any]] | Callable[..., AsyncIterator[Any]]
_Handles = TypeVar("_Handles", bound=Handler[Any, Any] | StreamHandler[Any, Any])
_Fn = TypeVar("_Fn", bound=_HandlerFn)
_Any = TypeVar("_Any", bound=type[Handler[Any, Any]] | type[StreamHandler[Any, Any]] | _HandlerFn)


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
    """Mark a class or async function as a handler, so ``Mediator.scan`` finds and registers it.

    Used bare, the handler serves the request named by the type hint of its request parameter:
    the first parameter of a function, or of a class's ``handle`` after ``self``. Given a request
    type, it serves that request whatever the hint says.

    A class handler is resolved through the mediator's ``Resolver`` for every send, or only once
    with ``lifetime="singleton"``. A function handler's parameters after the request are resolved
    through the ``Resolver`` by their type hints on every send. The handler of a stream request is
    an async generator (a function, or a class's ``handle``) that yields its items.

    Example:
        .. code-block:: python

            @handler
            class GetUserHandler:
                async def handle(self, request: GetUser) -> User: ...

            @handler(lifetime="singleton")
            class CachedGetUserHandler: ...

            @handler
            async def delete_user(request: DeleteUser, repo: UserRepository) -> None: ...

            @handler
            async def export_orders(request: ExportOrders) -> AsyncIterator[Order]:
                yield ...

    Raises:
        ValueError: ``lifetime`` is not "transient" or "singleton".

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
    """A handler bound to its request type, with how to call it for a request.

    ``returns`` is the handler's resolved return hint, or ``inspect.Signature.empty``. A handler
    that ``streams`` is an async generator: ``invoke`` returns its (unstarted) iterator.
    """

    request_type: type
    source: Any
    invoke: Invoke
    returns: Any = inspect.Signature.empty
    streams: bool = False


def bind(source: Any, request_type: type | None = None) -> Binding:
    """Bind a handler class or function to the request it serves.

    The request type is ``request_type``, else the one given to ``@handler(...)``, else the type
    hint of the request parameter. Forward references and deferred annotations resolve against
    the handler's module.

    Raises:
        InvalidHandlerSignature: the handler isn't an async function or a class with an async
            ``handle``, or a hint it needs is missing, unresolvable or (for the request) not a
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
        streams = inspect.isasyncgenfunction(handle)
        invoke = _class_invoker(source, lifetime, streams)
    else:
        function = require_async(
            source, source, "to be an `async def` function or a class", InvalidHandlerSignature
        )
        if lifetime != "transient":
            raise InvalidHandlerSignature(source, "only class handlers have a lifetime")
        params = shape(
            source, function, leading=("request",), method=False, error=InvalidHandlerSignature
        )
        streams = inspect.isasyncgenfunction(function)
        invoke = _function_invoker(function, params, streams)
    if request_type is None:
        request_type = _request_hint(source, params)
    returns = params.hints.get("return", inspect.Signature.empty)
    return Binding(request_type, source, invoke, returns, streams)


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


def _class_invoker(cls: type, lifetime: Lifetime, streams: bool) -> Invoke:
    if lifetime == "transient":

        async def instance(resolver: Resolver) -> Any:
            return await resolve(resolver, cls)

    else:
        instances: list[Any] = []

        async def instance(resolver: Resolver) -> Any:
            if not instances:
                resolved = await resolve(resolver, cls)
                if not instances:  # another send may have resolved it while this one awaited
                    instances.append(resolved)
            return instances[0]

    async def invoke(request: Any, resolver: Resolver) -> Any:
        items = (await instance(resolver)).handle(request)
        return items if streams else await items

    return invoke


def _function_invoker(fn: Callable[..., Any], params: Shape, streams: bool) -> Invoke:
    async def invoke(request: Any, resolver: Resolver) -> Any:
        args, kwargs = await params.dependencies(resolver)
        items = fn(request, *args, **kwargs)
        return items if streams else await items

    return invoke
