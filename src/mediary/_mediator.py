"""The mediator: routes requests and streams to their one handler, notifications to all theirs."""

import copy
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from functools import partial
from types import ModuleType
from typing import Any, Concatenate, Self, TypeVar, overload

from ._behaviors import Behavior, BehaviorBinding, StreamBehavior, bind_behavior, pipeline
from ._deprecation import positional_only
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidHandler,
    MediaryError,
    NotAMessage,
    NotANotification,
    RuleViolation,
    ScanError,
)
from ._handlers import Binding, Handler, StreamHandler, SyncHandler, bind
from ._markers import (
    HandlerInfo,
    Lifetime,
    Returns,
    Yields,
    is_notification,
    kind_of,
    marker_of,
)
from ._publishing import NotificationCall, PublishStrategy, Sequential
from ._resolving import DefaultResolver, Resolver
from ._scan import discover
from ._streaming import Stream, layer, through

_Req = TypeVar("_Req")
_R = TypeVar("_R")

_SCANNED_KINDS = frozenset({"handler", "behavior"})


@dataclass(frozen=True, slots=True)
class HandlerRegistration:
    """A handler registered with a mediator, and the message type it handles.

    ``handler`` is the class or function as it was registered. ``lifetime`` is how long the
    instance of a class handler lives; a function handler is always ``"transient"``.
    """

    message_type: type
    handler: Any
    lifetime: Lifetime = "transient"


@dataclass(frozen=True, slots=True)
class BehaviorRegistration:
    """A behavior added to a mediator, with its place in the pipeline and what it wraps.

    ``behavior`` is the class, instance or function as it was added. ``order`` and ``kinds`` are
    its place in the pipeline and the kinds of message it wraps (None for all), from ``use`` or
    ``@behavior(...)``. ``streams`` is whether it wraps stream requests, which only stream
    behaviors do: a behavior with both shapes, such as ``LoggingBehavior``, is added twice.
    """

    behavior: Any
    order: int = 0
    kinds: frozenset[str] | None = None
    streams: bool = False


@dataclass(frozen=True, slots=True)
class Registrations:
    """What a mediator has registered, as ``Mediator.registrations()`` returns it.

    ``handlers`` are ordered by the qualified name of their message type, then as ``publish``
    runs them. ``behaviors`` are in pipeline order, outermost first.
    """

    handlers: tuple[HandlerRegistration, ...] = ()
    behaviors: tuple[BehaviorRegistration, ...] = ()


@dataclass
class _Staged:
    """Handlers being added: one per sent or streamed message type, any number per notification."""

    requests: dict[type, Binding] = field(default_factory=dict[type, Binding])
    notifications: list[Binding] = field(default_factory=list[Binding])


class Mediator:
    """Sends requests to their handler and publishes notifications to theirs, via behaviors.

    It also streams the items of stream requests from their async generator handler.

    Each mediator has its own registrations; two mediators never share handlers or behaviors.
    Handler and behavior classes, and the dependencies of functions, come from ``resolver``,
    which defaults to calling each type with no arguments. ``publish_strategy`` runs the
    handlers of a notification; it defaults to ``Sequential()``.
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
        self._behaviors: dict[tuple[object, bool], BehaviorBinding] = {}
        self._pipelines: dict[type, tuple[BehaviorBinding, ...]] = {}

    @property
    def resolver(self) -> Resolver:
        """The resolver this mediator gets handler and behavior instances from."""
        return self._resolver

    def with_resolver(self, resolver: Resolver) -> Self:
        """Return a view of this mediator that resolves through ``resolver`` instead.

        The view shares everything else with this mediator, both ways and for good: its
        handlers, behaviors and publish strategy, and singleton handler instances. It is cheap
        to make, so make one per unit of work, such as per web request, with a resolver bound
        to that work's DI scope.

        Example:
            .. code-block:: python

                async with container() as request_container:
                    scoped = mediator.with_resolver(ContainerResolver(request_container))
                    await scoped.send(PlaceOrder("book", 1))

        """
        view = copy.copy(self)
        view._resolver = resolver
        return view

    @positional_only("request_type", "handler")
    def register(
        self,
        message_type: type[_Req],
        handler: type[Handler[_Req, Any]]
        | type[SyncHandler[_Req, Any]]
        | type[StreamHandler[_Req, Any]]
        | Callable[Concatenate[_Req, ...], Any],
        /,
    ) -> None:
        """Register ``handler``, a handler class or function, for ``message_type``.

        ``message_type`` is a request or a stream request, which has exactly one handler, or a
        notification, which has any number; or a message of another kind, such as a command.
        A stream request's handler is an async generator. A sync handler (a plain ``def``) runs
        on a worker thread. A class handler is resolved for every call, unless it is decorated
        with ``@handler(lifetime="singleton")``. Registering the same handler for the same type
        again changes nothing.

        Raises:
            NotAMessage: ``message_type`` isn't decorated as a kind of message, such as with
                ``@request`` or ``@notification``.
            InvalidHandler: ``handler`` has the wrong shape (see ``@handler``), or is an
                async generator for a message that isn't streamed, or isn't one for one that is.
            RuleViolation: ``handler`` breaks a rule of the kind of ``message_type``.
            DuplicateHandler: ``message_type`` has exactly one handler, and already has another.

        """
        staged = _Staged()
        self._stage(bind(handler, message_type), staged)
        self._commit(staged)

    def use(
        self,
        behavior: type[Behavior[Any, Any]]
        | type[StreamBehavior[Any, Any]]
        | Behavior[Any, Any]
        | StreamBehavior[Any, Any]
        | Callable[..., Awaitable[Any]]
        | Callable[..., AsyncIterator[Any]],
        *,
        order: int | None = None,
        kinds: Iterable[str] | None = None,
    ) -> None:
        """Add a behavior that isn't found by ``scan``, such as one from a library.

        ``behavior`` is a behavior class (resolved for every call), a configured instance (used
        as it is, e.g. ``RetryBehavior(max_retries=5)``) or an async function. ``order`` and
        ``kinds`` override those given to its ``@behavior(...)``, if any (see ``@behavior`` for what
        they mean). Adding a behavior that is already present changes nothing.

        Example:
            .. code-block:: python

                mediator.use(RetryBehavior(retry_on=(ConnectionError,)), kinds={"request"})

        Raises:
            InvalidBehavior: ``behavior`` has the wrong shape (see ``@behavior``), or ``kinds``
                names a kind that isn't defined.

        """
        self._add_behaviors(bind_behavior(behavior, order=order, kinds=kinds))

    def scan(self, *packages: str | ModuleType) -> None:
        """Import ``packages`` and their submodules; register every ``@handler`` and ``@behavior``.

        Each handler serves the message named by ``@handler(...)`` or by the type hint of its
        request parameter. Scanning is all or nothing: every problem found is reported
        together, and if there is any, nothing from this scan is registered. Scanning a
        package again registers nothing new.

        Raises:
            ScanError: a module failed to import, or a handler or behavior couldn't be
                registered (see ``register`` and ``use`` for the reasons).

        """
        found, problems = discover(packages, _SCANNED_KINDS)
        staged = _Staged()
        behaviors: list[BehaviorBinding] = []
        for obj in found:
            marker = marker_of(obj)
            try:
                if marker is not None and marker.kind == "behavior":
                    behaviors.extend(bind_behavior(obj))
                else:
                    self._stage(bind(obj), staged)
            except MediaryError as exc:
                problems.append(exc)
        if problems:
            raise ScanError(problems)
        self._commit(staged)
        self._add_behaviors(behaviors)

    def registrations(self) -> Registrations:
        """Return what this mediator has registered, with ``register``, ``use`` and ``scan``.

        It is a snapshot: later registrations don't change it. Use it for diagnostics, admin
        endpoints, or integrations that must know every handler class, like ``mediary.ext.dishka``.

        Example:
            .. code-block:: python

                for registration in mediator.registrations().handlers:
                    print(registration.message_type.__name__, registration.handler.__name__)

        """
        bindings = [*self._bindings.values()]
        for subscribers in self._subscribers.values():
            bindings.extend(subscribers.values())
        bindings.sort(key=lambda b: _qualified_name(b.request_type))  # stable: keeps publish order
        behaviors = sorted(self._behaviors.values(), key=lambda b: (b.order, b.name))
        return Registrations(
            tuple(
                HandlerRegistration(b.request_type, b.source, _lifetime(b.source)) for b in bindings
            ),
            tuple(BehaviorRegistration(b.source, b.order, b.kinds, b.streams) for b in behaviors),
        )

    def _stage(self, binding: Binding, staged: _Staged) -> None:
        """Add ``binding`` to ``staged``, or raise if it can't be registered."""
        target = binding.request_type
        kind = kind_of(target)
        if kind is None:
            raise NotAMessage(target)
        streamed = kind.dispatch == "stream"
        if binding.streams != streamed:
            raise InvalidHandler(
                binding.source,
                f"@{kind.name} handlers are async generators that `yield` their items"
                if streamed
                else f"it is an async generator, but @{kind.name} handlers `return` a result; "
                "only the handlers of stream requests `yield`",
            )
        handles = marker.handles if (marker := marker_of(binding.source)) is not None else None
        if handles is not None and handles != kind.name:
            raise RuleViolation(
                binding.source,
                kind.name,
                f"it handles only @{handles} messages, but {_qualified_name(target)} is a "
                f"@{kind.name}",
                target,
            )
        reason = kind.check(HandlerInfo(target, binding.source, binding.returns))
        if reason is not None:
            raise RuleViolation(binding.source, kind.name, reason, target)
        if kind.dispatch == "publish":
            staged.notifications.append(binding)
            return
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
            self._behaviors.setdefault((binding.source, binding.streams), binding)
        self._pipelines.clear()

    @overload
    async def send(self, request: Returns[_R], /) -> _R: ...
    @overload
    async def send(self, request: object, /) -> Any: ...
    async def send(self, request: object, /) -> Any:
        """Send ``request`` through its behaviors to its handler and return the result.

        The result is typed from the request's ``Returns[...]`` base, or ``Any`` without one.

        Raises:
            HandlerNotFound: no handler is registered for exactly ``type(request)``.

        """
        binding = self._bindings.get(type(request))
        if binding is None or binding.streams:
            raise HandlerNotFound(type(request))
        return await self._through_pipeline(
            request, partial(binding.invoke, request, self._resolver)
        )

    async def publish(
        self, notification: object, /, *, strategy: PublishStrategy | None = None
    ) -> None:
        """Publish ``notification`` through its behaviors to all of its handlers.

        The handlers, ordered by fully qualified name, are run by ``strategy``, or else by the
        mediator's publish strategy. Publishing a notification that has no handlers does
        nothing (its behaviors still run).

        Raises:
            NotANotification: ``type(notification)`` isn't decorated with ``@notification``.

        """
        notification_type = type(notification)
        if not is_notification(notification_type):
            raise NotANotification(notification_type)
        subscribers = self._subscribers.get(notification_type, {}).values()
        calls = [
            NotificationCall(
                b.source, notification, partial(b.invoke, notification, self._resolver)
            )
            for b in subscribers
        ]
        run = partial((strategy or self._strategy).publish, calls)
        await self._through_pipeline(notification, run)

    @overload
    def stream(self, request: Yields[_R], /) -> Stream[_R]: ...
    @overload
    def stream(self, request: object, /) -> Stream[Any]: ...
    def stream(self, request: object, /) -> Stream[Any]:
        """Stream the items ``request``'s handler yields, through its stream behaviors.

        Nothing runs until the stream is iterated. Iterate it inside ``async with`` to close the
        handler and behaviors as soon as the block exits (see ``Stream``). The items are typed
        from the request's ``Yields[...]`` base, or ``Any`` without one.

        Example:
            .. code-block:: python

                async with mediator.stream(ExportOrders(since)) as orders:
                    async for order in orders:
                        ...

        Raises:
            HandlerNotFound: no handler is registered for exactly ``type(request)``, as a
                stream request.

        """
        binding = self._bindings.get(type(request))
        if binding is None or not binding.streams:
            raise HandlerNotFound(type(request))
        return self._through_stream(request, partial(binding.invoke, request, self._resolver))

    def _through_stream(
        self, message: object, start: Callable[[], Awaitable[AsyncGenerator[Any, None]]]
    ) -> Stream[Any]:
        """Wrap the items of ``start()`` in the stream behaviors of ``type(message)``."""
        behaviors = self._pipeline(type(message))
        resolver = self._resolver

        def open(index: int) -> AsyncGenerator[Any, None]:
            if index == len(behaviors):
                return through(start)
            behavior = behaviors[index]
            return layer(
                lambda next: behavior.invoke(message, next, resolver), partial(open, index + 1)
            )

        return Stream(open(0))

    def _pipeline(self, message_type: type) -> tuple[BehaviorBinding, ...]:
        behaviors = self._pipelines.get(message_type)
        if behaviors is None:
            behaviors = self._pipelines[message_type] = pipeline(
                self._behaviors.values(), message_type
            )
        return behaviors

    async def _through_pipeline(
        self, message: object, terminal: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Run the behaviors that wrap ``type(message)`` around ``terminal``."""
        behaviors = self._pipeline(type(message))
        resolver = self._resolver

        async def call(index: int) -> Any:
            if index == len(behaviors):
                return await terminal()
            return await behaviors[index].invoke(message, partial(call, index + 1), resolver)

        return await call(0)


def _qualified_name(obj: object) -> str:
    return f"{getattr(obj, '__module__', '')}.{getattr(obj, '__qualname__', '')}"


def _lifetime(source: object) -> Lifetime:
    marker = marker_of(source) if isinstance(source, type) else None
    return marker.lifetime if marker is not None else "transient"
