"""The mediator: routes each request through its pipeline to its one handler."""

from collections.abc import Awaitable, Callable, Iterable, Mapping
from functools import partial
from types import ModuleType
from typing import Any, Concatenate, TypeVar, overload

from ._behaviors import Behavior, BehaviorBinding, bind_behavior, pipeline
from ._errors import DuplicateHandler, HandlerNotFound, MediaryError, NotARequest, ScanError
from ._handlers import Binding, Handler, bind
from ._markers import Returns, is_request, marker_of
from ._resolving import DefaultResolver, Resolver
from ._scan import discover

_Req = TypeVar("_Req")
_R = TypeVar("_R")

_SCANNED_KINDS = frozenset({"handler", "behavior"})


class Mediator:
    """Dispatches requests through their behaviors to their handlers.

    Each mediator has its own registrations; two mediators never share handlers or behaviors.
    Handler and behavior classes, and the dependencies of functions, come from `resolver`,
    which defaults to calling each type with no arguments.
    """

    def __init__(self, *, resolver: Resolver | None = None) -> None:
        self._resolver: Resolver = resolver if resolver is not None else DefaultResolver()
        self._bindings: dict[type, Binding] = {}
        self._behaviors: dict[object, BehaviorBinding] = {}
        self._pipelines: dict[type, tuple[BehaviorBinding, ...]] = {}

    def register(
        self,
        request_type: type[_Req],
        handler: type[Handler[_Req, Any]] | Callable[Concatenate[_Req, ...], Awaitable[Any]],
    ) -> None:
        """Register `handler`, a handler class or async function, for `request_type`.

        A class handler is resolved for every `send`, unless it is decorated with
        `@handler(lifetime="singleton")`. Registering the same handler for the same request
        again changes nothing.

        Raises:
            NotARequest: `request_type` isn't decorated with `@request`.
            InvalidHandlerSignature: `handler` has the wrong shape (see `@handler`).
            DuplicateHandler: `request_type` already has another handler.

        """
        binding = bind(handler, request_type)
        self._check(binding, {})
        self._bindings.setdefault(request_type, binding)

    def use(
        self,
        behavior: type[Behavior[Any, Any]] | Callable[..., Awaitable[Any]],
        *,
        order: int | None = None,
        kinds: Iterable[str] | None = None,
    ) -> None:
        """Add a behavior that isn't found by `scan`, such as one from a library.

        `order` and `kinds` override those given to its `@behavior(...)`, if any (see
        `@behavior` for what they mean). Adding a behavior that is already present changes
        nothing.

        Raises:
            InvalidBehaviorSignature: `behavior` has the wrong shape (see `@behavior`).

        """
        self._add_behaviors([bind_behavior(behavior, order=order, kinds=kinds)])

    def scan(self, *packages: str | ModuleType) -> None:
        """Import `packages` and all their submodules; register every `@handler` and `@behavior`.

        Each handler serves the request named by `@handler(...)` or by the type hint of its
        request parameter. Scanning is all or nothing: every problem found is reported
        together, and if there is any, nothing from this scan is registered. Scanning a
        package again registers nothing new.

        Raises:
            ScanError: a module failed to import, or a handler or behavior couldn't be
                registered (see `register` and `use` for the reasons).

        """
        found, problems = discover(packages, _SCANNED_KINDS)
        staged: dict[type, Binding] = {}
        behaviors: list[BehaviorBinding] = []
        for obj in found:
            marker = marker_of(obj)
            try:
                if marker is not None and marker.kind == "behavior":
                    behaviors.append(bind_behavior(obj))
                    continue
                binding = bind(obj)
                self._check(binding, staged)
            except MediaryError as exc:
                problems.append(exc)
            else:
                staged.setdefault(binding.request_type, binding)
        if problems:
            raise ScanError(problems)
        for request_type, binding in staged.items():
            self._bindings.setdefault(request_type, binding)
        self._add_behaviors(behaviors)

    def _check(self, binding: Binding, staged: Mapping[type, Binding]) -> None:
        if not is_request(binding.request_type):
            raise NotARequest(binding.request_type)
        existing = staged.get(binding.request_type) or self._bindings.get(binding.request_type)
        if existing is not None and existing.source is not binding.source:
            raise DuplicateHandler(binding.request_type, existing.source, binding.source)

    def _add_behaviors(self, behaviors: Iterable[BehaviorBinding]) -> None:
        for binding in behaviors:
            self._behaviors.setdefault(binding.source, binding)
        self._pipelines.clear()

    @overload
    async def send(self, request: Returns[_R], /) -> _R: ...
    @overload
    async def send(self, request: object, /) -> Any: ...
    async def send(self, request: object, /) -> Any:
        """Send `request` through its behaviors to its handler and return the result.

        The result is typed from the request's `Returns[...]` base, or `Any` without one.

        Raises:
            HandlerNotFound: no handler is registered for exactly `type(request)`.

        """
        request_type = type(request)
        binding = self._bindings.get(request_type)
        if binding is None:
            raise HandlerNotFound(request_type)
        behaviors = self._pipelines.get(request_type)
        if behaviors is None:
            behaviors = self._pipelines[request_type] = pipeline(
                self._behaviors.values(), request_type
            )
        resolver = self._resolver

        async def call(index: int) -> Any:
            if index == len(behaviors):
                return await binding.invoke(request, resolver)
            return await behaviors[index].invoke(request, partial(call, index + 1), resolver)

        return await call(0)
