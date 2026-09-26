"""The mediator: routes each request to its one handler."""

from collections.abc import Awaitable, Callable, Mapping
from types import ModuleType
from typing import Any, Concatenate, TypeVar, overload

from ._errors import DuplicateHandler, HandlerNotFound, MediaryError, NotARequest, ScanError
from ._handlers import Binding, DefaultResolver, Handler, Resolver, bind
from ._markers import Returns, is_request
from ._scan import discover

_Req = TypeVar("_Req")
_R = TypeVar("_R")


class Mediator:
    """Dispatches requests to their handlers.

    Each mediator has its own registrations; two mediators never share handlers. Handler
    classes and the dependencies of handler functions come from `resolver`, which defaults to
    calling each type with no arguments.
    """

    def __init__(self, *, resolver: Resolver | None = None) -> None:
        self._resolver: Resolver = resolver if resolver is not None else DefaultResolver()
        self._bindings: dict[type, Binding] = {}

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

    def scan(self, *packages: str | ModuleType) -> None:
        """Import `packages` and all their submodules, and register every `@handler` in them.

        Each handler serves the request named by `@handler(...)` or by the type hint of its
        request parameter. Scanning is all or nothing: every problem found is reported
        together, and if there is any, no handler from this scan is registered. Scanning a
        package again registers nothing new.

        Raises:
            ScanError: a module failed to import, or a handler couldn't be registered (see
                `register` for the reasons, plus unresolvable hints).

        """
        handlers, problems = discover(packages)
        staged: dict[type, Binding] = {}
        for handler in handlers:
            try:
                binding = bind(handler)
                self._check(binding, staged)
            except MediaryError as exc:
                problems.append(exc)
            else:
                staged.setdefault(binding.request_type, binding)
        if problems:
            raise ScanError(problems)
        for request_type, binding in staged.items():
            self._bindings.setdefault(request_type, binding)

    def _check(self, binding: Binding, staged: Mapping[type, Binding]) -> None:
        if not is_request(binding.request_type):
            raise NotARequest(binding.request_type)
        existing = staged.get(binding.request_type) or self._bindings.get(binding.request_type)
        if existing is not None and existing.source is not binding.source:
            raise DuplicateHandler(binding.request_type, existing.source, binding.source)

    @overload
    async def send(self, request: Returns[_R], /) -> _R: ...
    @overload
    async def send(self, request: object, /) -> Any: ...
    async def send(self, request: object, /) -> Any:
        """Send `request` to its handler and return the handler's result.

        The result is typed from the request's `Returns[...]` base, or `Any` without one.

        Raises:
            HandlerNotFound: no handler is registered for exactly `type(request)`.

        """
        binding = self._bindings.get(type(request))
        if binding is None:
            raise HandlerNotFound(type(request))
        return await binding.invoke(request, self._resolver)
