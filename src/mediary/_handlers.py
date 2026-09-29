"""Handlers: their shape, the ``@handler`` decorator, and binding one to its request."""

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Protocol, TypeVar, get_args, overload

from ._concurrency import run_sync
from ._errors import InvalidHandlerSignature
from ._markers import Kind, Lifetime, Marker, mark, marker_of
from ._resolving import Resolver, Shape, resolve, shape

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


class SyncHandler(Protocol[_Req_contra, _Res_co]):
    """The shape of a sync class handler: ``handle`` is a plain ``def``, run on a worker thread.

    Example:
        .. code-block:: python

            class GetUserHandler:
                def handle(self, request: GetUser) -> User:
                    return self.db.fetch_user(request.user_id)  # a blocking driver

    """

    def handle(self, request: _Req_contra, /) -> _Res_co:
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


_Handles = TypeVar(
    "_Handles", bound=Handler[Any, Any] | SyncHandler[Any, Any] | StreamHandler[Any, Any]
)
_Fn = TypeVar("_Fn", bound=Callable[..., Any])
_Any = TypeVar(
    "_Any",
    bound=type[Handler[Any, Any]]
    | type[SyncHandler[Any, Any]]
    | type[StreamHandler[Any, Any]]
    | Callable[..., Any],
)


# A class is also a `type`, and callable, so the overloads overlap by design: a class with
# `handle` matches first, then a request type (or nothing) given to configure the decorator,
# and any other callable is a function handler.
@overload
def handler(target: type[_Handles], /) -> type[_Handles]: ...  # pyright: ignore[reportOverlappingOverload]
@overload
def handler(
    request_type: type[object] | None = None, /, *, lifetime: Lifetime = "transient"
) -> Callable[[_Any], _Any]: ...
@overload
def handler(target: _Fn, /) -> _Fn: ...
def handler(target: Any = None, /, *, lifetime: Lifetime = "transient") -> Any:
    """Mark a class or function as a handler, so ``Mediator.scan`` finds and registers it.

    Used bare, the handler serves the request named by the type hint of its request parameter:
    the first parameter of a function, or of a class's ``handle`` after ``self``. Given a request
    type, it serves that request whatever the hint says.

    A class handler is resolved through the mediator's ``Resolver`` for every send, or only once
    with ``lifetime="singleton"``. A function handler's parameters after the request are resolved
    through the ``Resolver`` by their type hints on every send. The handler of a stream request is
    an async generator (a function, or a class's ``handle``) that yields its items.

    A handler that is a plain ``def`` function, or a class whose ``handle`` is a plain ``def``,
    runs on a worker thread, so a blocking call in it never blocks the event loop. Its class
    and dependencies are still resolved on the event loop.

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
            def get_report(request: GetReport, db: Database) -> Report:  # on a worker thread
                return db.build_report(request.month)

            @handler
            async def export_orders(request: ExportOrders) -> AsyncIterator[Order]:
                yield ...

    Raises:
        ValueError: ``lifetime`` is not "transient" or "singleton".

    """
    return _mark_handler(target, lifetime, None)


def _mark_handler(target: Any, lifetime: Lifetime, handles: str | None) -> Any:
    if lifetime not in _LIFETIMES:
        raise ValueError(f"lifetime must be one of {_LIFETIMES}, not {lifetime!r}")
    if inspect.isfunction(target) or hasattr(target, "handle"):
        return mark(target, Marker(kind="handler", lifetime=lifetime, handles=handles))

    def decorate(obj: _Any) -> _Any:
        return mark(obj, Marker(kind="handler", target=target, lifetime=lifetime, handles=handles))

    return decorate


class HandlerDecorator(Protocol):
    """The type of ``@handler``, and of the decorators ``handler_for`` makes."""

    @overload
    def __call__(self, target: type[_Handles], /) -> type[_Handles]: ...  # pyright: ignore[reportOverlappingOverload]
    @overload
    def __call__(
        self, request_type: type[object] | None = None, /, *, lifetime: Lifetime = "transient"
    ) -> Callable[[_Any], _Any]: ...
    @overload
    def __call__(self, target: _Fn, /) -> _Fn: ...


def handler_for(kind: Kind) -> HandlerDecorator:
    """Return a decorator like ``@handler`` for handlers of ``kind``'s messages only.

    It takes the same arguments as ``@handler``. A handler it marks is rejected when it is
    registered or scanned for a message of another kind, with a ``RuleViolation`` that names
    both, so a mismatch is found at startup rather than at dispatch.

    Example:
        .. code-block:: python

            report = define_kind("report", dispatch="send")
            report_handler = handler_for(report)

            @report_handler
            async def monthly_sales(request: MonthlySales) -> Report: ...

    """

    def decorate(target: Any = None, /, *, lifetime: Lifetime = "transient") -> Any:
        return _mark_handler(target, lifetime, kind.name)

    return decorate


Invoke = Callable[[Any, Resolver], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class Binding:
    """A handler bound to its request type, with how to call it for a request.

    ``returns`` is the handler's resolved return hint, or ``inspect.Signature.empty``. A handler
    that ``streams`` is an async generator: ``invoke`` returns its (unstarted) iterator. A sync
    handler, which is neither a coroutine nor an async generator function, runs on a worker
    thread.
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
        InvalidHandlerSignature: the handler isn't a function or a class with a ``handle``
            method, is a sync generator, or a hint it needs is missing, unresolvable or (for the
            request) not a single class.

    """
    marker = marker_of(source)
    if request_type is None and marker is not None:
        request_type = marker.target
    lifetime = marker.lifetime if marker is not None else "transient"
    if isinstance(source, type):
        handle = _require_handler(
            source, getattr(source, "handle", None), "a `handle(self, request)` method"
        )
        params = shape(
            source, handle, leading=("request",), method=True, error=InvalidHandlerSignature
        )
        streams = inspect.isasyncgenfunction(handle)
        invoke = _class_invoker(source, lifetime, streams, _is_sync(handle))
    else:
        function = _require_handler(source, source, "to be a function or a class")
        if lifetime != "transient":
            raise InvalidHandlerSignature(source, "only class handlers have a lifetime")
        params = shape(
            source, function, leading=("request",), method=False, error=InvalidHandlerSignature
        )
        streams = inspect.isasyncgenfunction(function)
        invoke = _function_invoker(function, params, streams, _is_sync(function))
    if request_type is None:
        request_type = _request_hint(source, params)
    returns = params.hints.get("return", inspect.Signature.empty)
    return Binding(request_type, source, invoke, returns, streams)


def _is_sync(fn: Callable[..., Any]) -> bool:
    return not (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn))


def _require_handler(source: Any, fn: Any, needs: str) -> Callable[..., Any]:
    """Return ``fn`` if it can handle a request, sync or async, else raise."""
    if inspect.isgeneratorfunction(fn):
        raise InvalidHandlerSignature(
            source,
            "it is a sync generator; the handlers of stream requests must be async generators "
            "(`async def` with `yield`)",
        )
    if not (inspect.isfunction(fn) or inspect.ismethod(fn)):
        raise InvalidHandlerSignature(source, f"it needs {needs}")
    return fn


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


def _class_invoker(cls: type, lifetime: Lifetime, streams: bool, sync: bool) -> Invoke:
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
        handle = (await instance(resolver)).handle
        if sync:
            return await run_sync(handle, request)
        items = handle(request)
        return items if streams else await items

    return invoke


def _function_invoker(fn: Callable[..., Any], params: Shape, streams: bool, sync: bool) -> Invoke:
    async def invoke(request: Any, resolver: Resolver) -> Any:
        args, kwargs = await params.dependencies(resolver)
        if sync:
            return await run_sync(partial(fn, request, *args, **kwargs))
        items = fn(request, *args, **kwargs)
        return items if streams else await items

    return invoke
