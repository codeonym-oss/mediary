"""The mediator: routes requests to their one handler and notifications to all of theirs."""

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from types import ModuleType
from typing import Any, Concatenate, TypeVar, overload

from ._behaviors import Behavior, BehaviorBinding, bind_behavior, pipeline
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    MediaryError,
    NotANotification,
    NotARequest,
    ScanError,
)
from ._handlers import Binding, Handler, bind
from ._markers import Returns, is_notification, is_request, marker_of
from ._publishing import PublishStrategy, Sequential
from ._resolving import DefaultResolver, Resolver
from ._scan import discover

_Req = TypeVar("_Req")
_R = TypeVar("_R")

_SCANNED_KINDS = frozenset({"handler", "behavior"})


@dataclass
class _Staged:
    """Handlers being added: one per request type, any number per notification type."""

    requests: dict[type, Binding] = field(default_factory=dict[type, Binding])
    notifications: list[Binding] = field(default_factory=list[Binding])


class Mediator:
    """Sends requests to their handler and publishes notifications to theirs, via behaviors.

    Each mediator has its own registrations; two mediators never share handlers or behaviors.
    Handler and behavior classes, and the dependencies of functions, come from `resolver`,
    which defaults to calling each type with no arguments. `publish_strategy` runs the
    handlers of a notification; it defaults to `Sequential()`.
    """

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        publish_strategy: PublishStrategy | None = None,
    ) -> None:
        self._resolver: Resolver = resolver if resolver is not None else DefaultResolver()
        self._strategy: PublishStrategy = publish_strategy or Sequential()
        self._bindings: dict[type, Binding] = {}
        self._subscribers: dict[type, dict[object, Binding]] = {}
        self._behaviors: dict[object, BehaviorBinding] = {}
        self._pipelines: dict[type, tuple[BehaviorBinding, ...]] = {}

    def register(
        self,
        request_type: type[_Req],
        handler: type[Handler[_Req, Any]] | Callable[Concatenate[_Req, ...], Awaitable[Any]],
    ) -> None:
        """Register `handler`, a handler class or async function, for `request_type`.

        `request_type` is a request, which has exactly one handler, or a notification, which
        has any number. A class handler is resolved for every call, unless it is decorated
        with `@handler(lifetime="singleton")`. Registering the same handler for the same type
        again changes nothing.

        Raises:
            NotARequest: `request_type` isn't decorated with `@request` or `@notification`.
            InvalidHandlerSignature: `handler` has the wrong shape (see `@handler`).
            DuplicateHandler: the request `request_type` already has another handler.

        """
        staged = _Staged()
        self._stage(bind(handler, request_type), staged)
        self._commit(staged)

    def use(
        self,
        behavior: type[Behavior[Any, Any]] | Behavior[Any, Any] | Callable[..., Awaitable[Any]],
        *,
        order: int | None = None,
        kinds: Iterable[str] | None = None,
    ) -> None:
        """Add a behavior that isn't found by `scan`, such as one from a library.

        `behavior` is a behavior class (resolved for every call), a configured instance (used
        as it is, e.g. `RetryBehavior(max_retries=5)`) or an async function. `order` and
        `kinds` override those given to its `@behavior(...)`, if any (see `@behavior` for what
        they mean). Adding a behavior that is already present changes nothing.

        Example:
            mediator.use(RetryBehavior(retry_on=(ConnectionError,)), kinds={"request"})


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
        staged = _Staged()
        behaviors: list[BehaviorBinding] = []
        for obj in found:
            marker = marker_of(obj)
            try:
                if marker is not None and marker.kind == "behavior":
                    behaviors.append(bind_behavior(obj))
                else:
                    self._stage(bind(obj), staged)
            except MediaryError as exc:
                problems.append(exc)
        if problems:
            raise ScanError(problems)
        self._commit(staged)
        self._add_behaviors(behaviors)

    def _stage(self, binding: Binding, staged: _Staged) -> None:
        """Add `binding` to `staged`, or raise if it can't be registered."""
        target = binding.request_type
        if is_notification(target):
            staged.notifications.append(binding)
            return
        if not is_request(target):
            raise NotARequest(target)
        existing = staged.requests.get(target) or self._bindings.get(target)
        if existing is not None and existing.source is not binding.source:
            raise DuplicateHandler(target, existing.source, binding.source)
        staged.requests.setdefault(target, binding)

    def _commit(self, staged: _Staged) -> None:
        for request_type, binding in staged.requests.items():
            self._bindings.setdefault(request_type, binding)
        for binding in staged.notifications:
            subscribers = self._subscribers.setdefault(binding.request_type, {})
            subscribers.setdefault(binding.source, binding)
            ordered = sorted(subscribers.values(), key=lambda b: _qualified_name(b.source))
            self._subscribers[binding.request_type] = {b.source: b for b in ordered}

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
        binding = self._bindings.get(type(request))
        if binding is None:
            raise HandlerNotFound(type(request))
        return await self._through_pipeline(
            request, partial(binding.invoke, request, self._resolver)
        )

    async def publish(
        self, notification: object, /, *, strategy: PublishStrategy | None = None
    ) -> None:
        """Publish `notification` through its behaviors to all of its handlers.

        The handlers, ordered by fully qualified name, are run by `strategy`, or else by the
        mediator's publish strategy. Publishing a notification that has no handlers does
        nothing (its behaviors still run).

        Raises:
            NotANotification: `type(notification)` isn't decorated with `@notification`.

        """
        notification_type = type(notification)
        if not is_notification(notification_type):
            raise NotANotification(notification_type)
        subscribers = self._subscribers.get(notification_type, {}).values()
        handlers = [partial(b.invoke, notification, self._resolver) for b in subscribers]
        run = partial((strategy or self._strategy).publish, handlers)
        await self._through_pipeline(notification, run)

    async def _through_pipeline(
        self, message: object, terminal: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Run the behaviors that wrap `type(message)` around `terminal`."""
        message_type = type(message)
        behaviors = self._pipelines.get(message_type)
        if behaviors is None:
            behaviors = self._pipelines[message_type] = pipeline(
                self._behaviors.values(), message_type
            )
        resolver = self._resolver

        async def call(index: int) -> Any:
            if index == len(behaviors):
                return await terminal()
            return await behaviors[index].invoke(message, partial(call, index + 1), resolver)

        return await call(0)


def _qualified_name(obj: object) -> str:
    return f"{getattr(obj, '__module__', '')}.{getattr(obj, '__qualname__', '')}"
