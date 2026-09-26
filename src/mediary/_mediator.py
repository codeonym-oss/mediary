"""The mediator: routes each request to its one handler."""

import inspect
from typing import Any, Protocol, TypeVar, overload

from ._errors import DuplicateHandler, HandlerNotFound, InvalidHandlerSignature, NotARequest
from ._markers import Returns, marker_of

_Req = TypeVar("_Req")
_Req_contra = TypeVar("_Req_contra", contravariant=True)
_Res_co = TypeVar("_Res_co", covariant=True)
_R = TypeVar("_R")


class Handler(Protocol[_Req_contra, _Res_co]):
    """The shape of a request handler: any class with an async `handle` taking the request.

    No base class is needed; type checkers match handlers structurally.

    Example:
        class GetUserHandler:
            async def handle(self, request: GetUser) -> User: ...

    """

    async def handle(self, request: _Req_contra, /) -> _Res_co:
        """Handle `request` and return its result."""
        ...


class Mediator:
    """Dispatches requests to their handlers.

    Each mediator has its own registrations; two mediators never share handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, type[Handler[Any, Any]]] = {}

    def register(self, request_type: type[_Req], handler: type[Handler[_Req, Any]]) -> None:
        """Register `handler` as the handler of `request_type`.

        A new handler instance is created for every `send`.

        Raises:
            NotARequest: `request_type` isn't decorated with `@request`.
            InvalidHandlerSignature: `handler` has no async `handle` method.
            DuplicateHandler: `request_type` already has a handler.

        """
        if marker_of(request_type) is None:
            raise NotARequest(request_type)
        if not inspect.iscoroutinefunction(getattr(handler, "handle", None)):
            raise InvalidHandlerSignature(handler, "it needs an `async def handle(self, request)`")
        existing = self._handlers.get(request_type)
        if existing is not None:
            raise DuplicateHandler(request_type, existing, handler)
        self._handlers[request_type] = handler

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
