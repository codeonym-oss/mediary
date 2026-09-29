"""Pipeline behaviors: middleware around handlers, and which requests each one wraps."""

import inspect
import sys
import types
import typing
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, TypeVar, Union, overload

from ._errors import InvalidBehaviorSignature
from ._markers import Marker, kind_of, mark, marker_of
from ._resolving import Resolver, Shape, require_async, resolve, shape

_R = TypeVar("_R")
_Req_contra = TypeVar("_Req_contra", contravariant=True)

Next: TypeAlias = Callable[[], Awaitable[_R]]
"""Calls the rest of the pipeline (the next behavior, or the handler) and returns its result."""

NextStream: TypeAlias = Callable[[], AsyncIterator[_R]]
"""Opens the rest of a stream's pipeline (the next behavior, or the handler) as an iterator."""


class Behavior(Protocol[_Req_contra, _R]):
    """The shape of a class behavior: an async ``handle`` taking the request and ``next``.

    A behavior runs code around the rest of the pipeline. It may call ``next()`` any number of
    times (zero to short-circuit, more to retry) and may change the result.

    Example:
        .. code-block:: python

            class Timing:
                async def handle(self, request: object, next: Next[T]) -> T:
                    started = time.perf_counter()
                    try:
                        return await next()
                    finally:
                        log(type(request), time.perf_counter() - started)

    """

    async def handle(self, request: _Req_contra, next: Next[_R], /) -> _R:
        """Handle ``request``, usually by awaiting ``next()``."""
        ...


class StreamBehavior(Protocol[_Req_contra, _R]):
    """The shape of a class behavior around stream requests: ``handle`` is an async generator.

    It yields the items of the rest of the pipeline, which it opens by calling ``next()``. It
    may filter, transform, add or count items, and run code before and after the stream.
    Iterators it gets from ``next()`` are closed when it is, even if it doesn't close them.

    Example:
        .. code-block:: python

            class Counting:
                async def handle(self, request: object, next: NextStream[T]) -> AsyncIterator[T]:
                    count = 0
                    async for item in next():
                        count += 1
                        yield item
                    log(type(request), count)

    """

    def handle(self, request: _Req_contra, next: NextStream[_R], /) -> AsyncIterator[_R]:
        """Yield the items of ``request``, usually those of ``next()``."""
        ...


_BehaviorFn = Callable[..., Awaitable[Any]] | Callable[..., AsyncIterator[Any]]
_Behaves = TypeVar("_Behaves", bound=Behavior[Any, Any] | StreamBehavior[Any, Any])
_Fn = TypeVar("_Fn", bound=_BehaviorFn)
_Any = TypeVar(
    "_Any", bound=type[Behavior[Any, Any]] | type[StreamBehavior[Any, Any]] | _BehaviorFn
)


@overload
def behavior(target: type[_Behaves], /) -> type[_Behaves]: ...
@overload
def behavior(target: _Fn, /) -> _Fn: ...
@overload
def behavior(*, order: int = 0, kinds: Iterable[str] | None = None) -> Callable[[_Any], _Any]: ...
def behavior(target: Any = None, /, *, order: int = 0, kinds: Iterable[str] | None = None) -> Any:
    """Mark a class or async function as a pipeline behavior, so ``Mediator.scan`` adds it.

    A behavior wraps the requests its request parameter's hint matches: every request when the
    hint is missing, ``object`` or ``Any``; subclasses of a class; classes that have every member
    of a Protocol; or any member of a union. ``kinds`` further limits it to requests whose
    decorator has one of those kinds, such as ``{"request"}``.

    A behavior whose ``handle`` (or the function itself) is an async generator is a stream
    behavior: it wraps only stream requests, and gets ``next`` as a ``NextStream``. Every other
    behavior wraps only the requests and notifications that are sent or published. A class
    whose async ``handle`` wraps those can wrap streams too, with an async generator
    ``handle_stream(self, request, next)``; the two share the class's ``order`` and ``kinds``.

    Behaviors with a lower ``order`` run outside those with a higher one; ties are ordered by
    fully qualified name. A class behavior is resolved through the ``Resolver`` for every send.
    A function behavior's parameters after ``next`` are resolved by their type hints.

    Example:
        .. code-block:: python

            @behavior(order=-10)
            class Logging:
                async def handle(self, request: object, next: Next[T]) -> T: ...

            @behavior(kinds={"request"})
            async def in_transaction(request: object, next: Next[T], db: Database) -> T: ...

    Raises:
        TypeError: ``kinds`` is a single string rather than a collection of them.

    """
    marker = Marker(kind="behavior", order=order, kinds=_kinds(kinds))
    if target is not None:
        return mark(target, marker)

    def decorate(obj: _Any) -> _Any:
        return mark(obj, marker)

    return decorate


def _kinds(kinds: Iterable[str] | None) -> frozenset[str] | None:
    if isinstance(kinds, str):
        raise TypeError(f"kinds must be a collection of kind names, like {{{kinds!r}}}")
    return None if kinds is None else frozenset(kinds)


InvokeBehavior = Callable[[Any, Any, Resolver], Awaitable[Any]]
"""Calls a behavior with ``(request, next, resolver)``; a stream behavior's returns an iterator."""


@dataclass(frozen=True, slots=True)
class BehaviorBinding:
    """A behavior with its pipeline position, what it wraps, and how to call it.

    A behavior that ``streams`` is an async generator: ``invoke`` returns its (unstarted) iterator.
    """

    source: Any
    order: int
    name: str
    targets: tuple[type, ...] | None
    kinds: frozenset[str] | None
    invoke: InvokeBehavior
    streams: bool = False

    def wraps(self, request_type: type) -> bool:
        """Whether this behavior belongs in the pipeline of ``request_type``."""
        kind = kind_of(request_type)
        if self.streams != (kind is not None and kind.dispatch == "stream"):
            return False
        if self.kinds is not None:
            marker = marker_of(request_type)
            if marker is None or marker.kind not in self.kinds:
                return False
        return self.targets is None or any(_matches(request_type, t) for t in self.targets)


_LEADING = ("request", "next")


def bind_behavior(
    source: Any, *, order: int | None = None, kinds: Iterable[str] | None = None
) -> list[BehaviorBinding]:
    """Bind a behavior class, function or instance; ``order`` and ``kinds`` override the decorator.

    A class is resolved through the ``Resolver`` on every call; an instance is used as it is.
    There is one binding, or two for a class with both ``handle`` and ``handle_stream``.

    Raises:
        InvalidBehaviorSignature: it isn't an async function, or a class or instance with an
            async ``handle`` taking ``(request, next)``, or its ``handle_stream`` isn't an async
            generator beside a ``handle`` that isn't one, or its hints are unresolvable or
            target no class.

    """
    marker = marker_of(source)
    order = order if order is not None else marker.order if marker is not None else 0
    kinds = _kinds(kinds) if kinds is not None else marker.kinds if marker else None
    if not isinstance(source, type) and (
        inspect.isfunction(source) or not hasattr(source, "handle")
    ):
        function = require_async(
            source, source, "to be an `async def` function or a class", InvalidBehaviorSignature
        )
        params = shape(
            source, function, leading=_LEADING, method=False, error=InvalidBehaviorSignature
        )
        streams = inspect.isasyncgenfunction(function)
        invoke = _function_invoker(function, params, streams)
        return [_binding(source, source, order, kinds, params, invoke, streams)]
    cls = source if isinstance(source, type) else type(source)
    handle = require_async(
        source,
        getattr(cls, "handle", None),
        "an `async def handle(self, request, next)`",
        InvalidBehaviorSignature,
    )
    methods = [("handle", handle)]
    handle_stream = getattr(cls, "handle_stream", None)
    if handle_stream is not None:
        if inspect.isasyncgenfunction(handle) or not inspect.isasyncgenfunction(handle_stream):
            raise InvalidBehaviorSignature(
                source,
                "`handle_stream` must be an async generator, beside a `handle` that isn't one",
            )
        methods.append(("handle_stream", handle_stream))
    bindings: list[BehaviorBinding] = []
    for name, method in methods:
        params = shape(
            source, method, leading=_LEADING, method=True, error=InvalidBehaviorSignature
        )
        streams = inspect.isasyncgenfunction(method)
        invoke = (
            _class_invoker(source, name, streams)
            if source is cls
            else _instance_invoker(source, name, streams)
        )
        bindings.append(_binding(source, cls, order, kinds, params, invoke, streams))
    return bindings


def _binding(
    source: Any,
    cls: Any,
    order: int,
    kinds: frozenset[str] | None,
    params: Shape,
    invoke: InvokeBehavior,
    streams: bool,
) -> BehaviorBinding:
    return BehaviorBinding(
        source=source,
        order=order,
        name=f"{cls.__module__}.{cls.__qualname__}",
        targets=_targets(source, params),
        kinds=kinds,
        invoke=invoke,
        streams=streams,
    )


def pipeline(
    behaviors: Iterable[BehaviorBinding], request_type: type
) -> tuple[BehaviorBinding, ...]:
    """Return the behaviors wrapping ``request_type``, outermost first."""
    wrapping = (b for b in behaviors if b.wraps(request_type))
    return tuple(sorted(wrapping, key=lambda b: (b.order, b.name)))


def _targets(source: Any, params: Shape) -> tuple[type, ...] | None:
    hint = params.hint(0)
    if hint is None or hint is object or hint is Any:
        return None
    members = typing.get_args(hint) if typing.get_origin(hint) in (Union, types.UnionType) else ()
    targets = members or (hint,)
    if not all(isinstance(t, type) for t in targets):
        raise InvalidBehaviorSignature(
            source,
            f"the request parameter `{params.leading[0].name}` must be hinted with a class, a "
            f"Protocol or a union of them, not {hint!r}",
        )
    return targets


def _matches(request_type: type, target: type) -> bool:
    if getattr(target, "_is_protocol", False):
        return _protocol_members(target) <= _attributes(request_type)
    return issubclass(request_type, target)


def _protocol_members(protocol: type) -> frozenset[str]:
    members = getattr(protocol, "__protocol_attrs__", None)
    if members is None:  # Python 3.11 only computes them on demand
        members = getattr(typing, "_get_protocol_attrs")(protocol)  # noqa: B009
    return frozenset(members)


def _attributes(cls: type) -> frozenset[str]:
    """Return the attribute names of ``cls`` instances: class attributes and annotated fields."""
    names = set(dir(cls))
    for klass in cls.__mro__:
        names.update(_annotation_names(klass))
    return frozenset(names)


def _annotation_names(cls: type) -> Iterable[str]:
    if sys.version_info >= (3, 14):
        import annotationlib

        return annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
    return inspect.get_annotations(cls)


def _class_invoker(cls: type, method: str, streams: bool) -> InvokeBehavior:
    async def invoke(request: Any, next: Any, resolver: Resolver) -> Any:
        result = getattr(await resolve(resolver, cls), method)(request, next)
        return result if streams else await result

    return invoke


def _instance_invoker(instance: Any, method: str, streams: bool) -> InvokeBehavior:
    handle = getattr(instance, method)

    async def invoke(request: Any, next: Any, resolver: Resolver) -> Any:
        result = handle(request, next)
        return result if streams else await result

    return invoke


def _function_invoker(fn: Callable[..., Any], params: Shape, streams: bool) -> InvokeBehavior:
    async def invoke(request: Any, next: Any, resolver: Resolver) -> Any:
        args, kwargs = await params.dependencies(resolver)
        result = fn(request, next, *args, **kwargs)
        return result if streams else await result

    return invoke
