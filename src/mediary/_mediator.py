"""The mediator: routes each request to its one handler."""

from collections.abc import Mapping
from types import ModuleType
from typing import Any, TypeVar, overload

from ._errors import DuplicateHandler, HandlerNotFound, MediaryError, NotARequest, ScanError
from ._handlers import Handler, bound_request, check_handle
from ._markers import Returns, is_request
from ._scan import discover

_Req = TypeVar("_Req")
_R = TypeVar("_R")


class Mediator:
    """Dispatches requests to their handlers.

    Each mediator has its own registrations; two mediators never share handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, type[Handler[Any, Any]]] = {}

    def register(self, request_type: type[_Req], handler: type[Handler[_Req, Any]]) -> None:
        """Register `handler` as the handler of `request_type`.

        A new handler instance is created for every `send`. Registering the same handler for
        the same request again changes nothing.

        Raises:
            NotARequest: `request_type` isn't decorated with `@request`.
            InvalidHandlerSignature: `handler` has no async `handle` method.
            DuplicateHandler: `request_type` already has another handler.

        """
        self._check(request_type, handler, {})
        self._handlers[request_type] = handler

    def scan(self, *packages: str | ModuleType) -> None:
        """Import `packages` and all their submodules, and register every `@handler` in them.

        Each handler serves the request named by `@handler(...)` or by the type hint of its
        `handle` method's request parameter. Scanning is all or nothing: every problem found is
        reported together, and if there is any, no handler from this scan is registered.
        Scanning a package again registers nothing new.

        Raises:
            ScanError: a module failed to import, or a handler couldn't be registered (see
                `register` for the reasons, plus unresolvable request hints).

        """
        handlers, problems = discover(packages)
        staged: dict[type, type[Handler[Any, Any]]] = {}
        for handler in handlers:
            try:
                request_type = bound_request(handler)
                self._check(request_type, handler, staged)
            except MediaryError as exc:
                problems.append(exc)
            else:
                staged[request_type] = handler
        if problems:
            raise ScanError(problems)
        self._handlers.update(staged)

    def _check(
        self, request_type: type, handler: type, staged: Mapping[type, type[Handler[Any, Any]]]
    ) -> None:
        if not is_request(request_type):
            raise NotARequest(request_type)
        check_handle(handler)
        existing = staged.get(request_type) or self._handlers.get(request_type)
        if existing is not None and existing is not handler:
            raise DuplicateHandler(request_type, existing, handler)

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
        handler = self._handlers.get(type(request))
        if handler is None:
            raise HandlerNotFound(type(request))
        return await handler().handle(request)
