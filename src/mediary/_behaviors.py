"""Pipeline behaviors: middleware around handlers, and which requests each one wraps."""

import inspect
import sys
import types
import typing
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias, TypeVar, Union, overload

from ._errors import InvalidBehaviorSignature
from ._markers import Marker, mark, marker_of
from ._resolving import Resolver, Shape, require_async, resolve, shape

_R = TypeVar("_R")
_Req_contra = TypeVar("_Req_contra", contravariant=True)

Next: TypeAlias = Callable[[], Awaitable[_R]]
"""Calls the rest of the pipeline (the next behavior, or the handler) and returns its result."""


class Behavior(Protocol[_Req_contra, _R]):
    """The shape of a class behavior: an async `handle` taking the request and `next`.

    A behavior runs code around the rest of the pipeline. It may call `next()` any number of
    times (zero to short-circuit, more to retry) and may change the result.

    Example:
        class Timing:
            async def handle(self, request: object, next: Next[T]) -> T:
                started = time.perf_counter()
                try:
                    return await next()
                finally:
                    log(type(request), time.perf_counter() - started)

    """

    async def handle(self, request: _Req_contra, next: Next[_R], /) -> _R:
        """Handle `request`, usually by awaiting `next()`."""
        ...


_Behaves = TypeVar("_Behaves", bound=Behavior[Any, Any])
_Fn = TypeVar("_Fn", bound=Callable[..., Awaitable[Any]])
_Any = TypeVar("_Any", bound=type[Behavior[Any, Any]] | Callable[..., Awaitable[Any]])


@overload
def behavior(target: type[_Behaves], /) -> type[_Behaves]: ...
@overload
def behavior(target: _Fn, /) -> _Fn: ...
@overload
def behavior(*, order: int = 0, kinds: Iterable[str] | None = None) -> Callable[[_Any], _Any]: ...
def behavior(target: Any = None, /, *, order: int = 0, kinds: Iterable[str] | None = None) -> Any:
    """Mark a class or async function as a pipeline behavior, so `Mediator.scan` adds it.

    A behavior wraps the requests its request parameter's hint matches: every request when the
    hint is missing, `object` or `Any`; subclasses of a class; classes that have every member
    of a Protocol; or any member of a union. `kinds` further limits it to requests whose
    decorator has one of those kinds, such as `{"request"}`.

    Behaviors with a lower `order` run outside those with a higher one; ties are ordered by
    fully qualified name. A class behavior is resolved through the `Resolver` for every send.
    A function behavior's parameters after `next` are resolved by their type hints.

    Example:
        @behavior(order=-10)
        class Logging:
            async def handle(self, request: object, next: Next[T]) -> T: ...

        @behavior(kinds={"request"})
        async def in_transaction(request: object, next: Next[T], db: Database) -> T: ...

    Raises:
        TypeError: `kinds` is a single string rather than a collection of them.

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


InvokeBehavior = Callable[[Any, Next[Any], Resolver], Awaitable[Any]]


@dataclass(frozen=True, slots=True)
class BehaviorBinding:
    """A behavior with its pipeline position, what it wraps, and how to call it."""

    source: Any
    order: int
    name: str
    targets: tuple[type, ...] | None
    kinds: frozenset[str] | None
    invoke: InvokeBehavior

    def wraps(self, request_type: type) -> bool:
        """Whether this behavior belongs in the pipeline of `request_type`."""
        if self.kinds is not None:
            marker = marker_of(request_type)
            if marker is None or marker.kind not in self.kinds:
                return False
        return self.targets is None or any(_matches(request_type, t) for t in self.targets)


def bind_behavior(
    source: Any, *, order: int | None = None, kinds: Iterable[str] | None = None
) -> BehaviorBinding:
    """Bind a behavior class or function; `order` and `kinds` override its decorator's.

    Raises:
        InvalidBehaviorSignature: it isn't an async function or a class with an async `handle`
            taking `(request, next)`, or its hints are unresolvable or target no class.

    """
    marker = marker_of(source)
    if isinstance(source, type):
        handle = require_async(
            source,
            getattr(source, "handle", None),
            "an `async def handle(self, request, next)`",
            InvalidBehaviorSignature,
        )
        params = shape(
            source, handle, leading=("request", "next"), method=True, error=InvalidBehaviorSignature
        )
        invoke = _class_invoker(source)
    else:
        function = require_async(
            source, source, "to be an `async def` function or a class", InvalidBehaviorSignature
        )
        params = shape(
            source,
            function,
            leading=("request", "next"),
            method=False,
            error=InvalidBehaviorSignature,
        )
        invoke = _function_invoker(function, params)
    return BehaviorBinding(
        source=source,
        order=order if order is not None else marker.order if marker is not None else 0,
        name=f"{source.__module__}.{source.__qualname__}",
        targets=_targets(source, params),
        kinds=_kinds(kinds) if kinds is not None else marker.kinds if marker else None,
        invoke=invoke,
    )


def pipeline(
    behaviors: Iterable[BehaviorBinding], request_type: type
) -> tuple[BehaviorBinding, ...]:
    """Return the behaviors wrapping `request_type`, outermost first."""
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
    """Return the attribute names of `cls` instances: class attributes and annotated fields."""
    names = set(dir(cls))
    for klass in cls.__mro__:
        names.update(_annotation_names(klass))
    return frozenset(names)


def _annotation_names(cls: type) -> Iterable[str]:
    if sys.version_info >= (3, 14):
        import annotationlib

        return annotationlib.get_annotations(cls, format=annotationlib.Format.FORWARDREF)
    return inspect.get_annotations(cls)


def _class_invoker(cls: type) -> InvokeBehavior:
    async def invoke(request: Any, next: Next[Any], resolver: Resolver) -> Any:
        return await (await resolve(resolver, cls)).handle(request, next)

    return invoke


def _function_invoker(fn: Callable[..., Awaitable[Any]], params: Shape) -> InvokeBehavior:
    async def invoke(request: Any, next: Next[Any], resolver: Resolver) -> Any:
        args, kwargs = await params.dependencies(resolver)
        return await fn(request, next, *args, **kwargs)

    return invoke
