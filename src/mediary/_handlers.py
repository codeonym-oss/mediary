"""Handlers: their shape, the `@handler` decorator, and binding one to its request."""

import inspect
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, get_args, overload

from ._errors import InvalidHandlerSignature
from ._markers import Lifetime, Marker, mark, marker_of

_T = TypeVar("_T")
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


class Resolver(Protocol):
    """Supplies handler instances and the dependencies of function handlers.

    Plug a DI container in by adapting it to `resolve`, which may be sync or async. The
    default resolver calls `cls()`.

    Example:
        class ContainerResolver:
            def __init__(self, container: Container) -> None:
                self.container = container

            def resolve(self, cls: type[T]) -> T:
                return self.container.get(cls)

        mediator = Mediator(resolver=ContainerResolver(container))

    """

    def resolve(self, cls: type[_T], /) -> _T | Awaitable[_T]:
        """Return an instance of `cls`."""
        ...


class DefaultResolver:
    """Instantiates each type with no arguments."""

    def resolve(self, cls: type[_T], /) -> _T:
        """Return `cls()`."""
        return cls()


async def resolve(resolver: Resolver, cls: Any) -> Any:
    """Resolve `cls` with `resolver`, awaiting the result if it is awaitable."""
    instance = resolver.resolve(cls)
    return await instance if inspect.isawaitable(instance) else instance


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


def is_handler(obj: object) -> bool:
    """Whether `obj` itself is decorated with `@handler`."""
    marker = marker_of(obj)
    return marker is not None and marker.kind == "handler"


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
        handle = _async(
            source, getattr(source, "handle", None), "an `async def handle(self, request)`"
        )
        params, hints = _signature(source, handle, skip_self=True)
        if request_type is None:
            request_type = _request_hint(source, params, hints)
        return Binding(request_type, source, _class_invoker(source, lifetime))
    function = _async(source, source, "to be an `async def` function or a class")
    if lifetime != "transient":
        raise InvalidHandlerSignature(source, "only class handlers have a lifetime")
    params, hints = _signature(source, function, skip_self=False)
    if request_type is None:
        request_type = _request_hint(source, params, hints)
    return Binding(request_type, source, _function_invoker(source, params, hints))


def _async(source: Any, fn: Any, needs: str) -> Callable[..., Awaitable[Any]]:
    if not inspect.iscoroutinefunction(fn):
        raise InvalidHandlerSignature(source, f"it needs {needs}")
    return fn


def _signature(
    source: Any, fn: Callable[..., Any], *, skip_self: bool
) -> tuple[list[inspect.Parameter], dict[str, Any]]:
    params = list(inspect.signature(fn).parameters.values())[1 if skip_self else 0 :]
    if not params or params[0].kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        raise InvalidHandlerSignature(source, "it takes no positional request parameter")
    for param in params[1:]:
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise InvalidHandlerSignature(
                source, f"dependencies are resolved one by one, so `{param}` isn't allowed"
            )
    try:
        hints = typing.get_type_hints(fn)
    except Exception as exc:
        raise InvalidHandlerSignature(
            source, f"cannot resolve its type hints ({type(exc).__name__}: {exc})"
        ) from exc
    return params, hints


def _request_hint(source: Any, params: list[inspect.Parameter], hints: dict[str, Any]) -> type:
    name = params[0].name
    hint = hints.get(name)
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


def _function_invoker(
    fn: Callable[..., Awaitable[Any]], params: list[inspect.Parameter], hints: dict[str, Any]
) -> Invoke:
    positional: list[Any] = []
    keyword: dict[str, Any] = {}
    for param in params[1:]:
        if param.name not in hints:
            raise InvalidHandlerSignature(
                fn, f"the dependency `{param.name}` needs a type hint so it can be resolved"
            )
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(hints[param.name])
        else:
            keyword[param.name] = hints[param.name]

    async def invoke(request: Any, resolver: Resolver) -> Any:
        args = [await resolve(resolver, hint) for hint in positional]
        kwargs = {name: await resolve(resolver, hint) for name, hint in keyword.items()}
        return await fn(request, *args, **kwargs)

    return invoke
