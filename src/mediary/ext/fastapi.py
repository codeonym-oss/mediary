"""Use a mediator from FastAPI endpoints: `pip install mediary[fastapi]`.

`setup_mediary` attaches a mediator to the app; endpoints then take `MediatorDep`, a view of
it (see `Mediator.with_resolver`) for the current request or websocket. Handlers and their
dependencies can ask for that `Request` or `WebSocket`; everything else is resolved by the
mediator's own resolver, or by a resolver you make for each connection.

Example:
    app = FastAPI()
    mediator = Mediator()
    mediator.scan("app")
    setup_mediary(app, mediator)

    @app.post("/orders")
    async def place_order(order: PlaceOrder, mediator: MediatorDep) -> int:
        return await mediator.send(order)

With a DI container such as dishka, use its FastAPI integration and `mediary.ext.dishka`
instead, for request-scoped dependencies.

"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

from fastapi import Depends, FastAPI
from starlette.requests import HTTPConnection, Request
from starlette.websockets import WebSocket

from .._mediator import Mediator
from .._resolving import Resolver

__all__ = ["ConnectionResolver", "MediatorDep", "get_mediator", "setup_mediary"]

_T = TypeVar("_T")

_CONNECTIONS: tuple[type, ...] = (HTTPConnection, Request, WebSocket)

ResolverFactory = Callable[[HTTPConnection], Resolver]
"""Makes the resolver for one request or websocket."""


class ConnectionResolver:
    """A `Resolver` that supplies the current connection, and delegates everything else.

    Asked for `Request`, `WebSocket` or `HTTPConnection`, it returns the connection if it is
    one; any other type comes from `fallback`.
    """

    def __init__(self, connection: HTTPConnection, fallback: Resolver) -> None:
        """Supply `connection`, and resolve everything else through `fallback`."""
        self.connection = connection
        self.fallback = fallback

    def resolve(self, cls: type[_T], /) -> Any:
        """Return the connection if it is a `cls`, else `fallback.resolve(cls)`."""
        if cls in _CONNECTIONS and isinstance(self.connection, cls):
            return self.connection
        return self.fallback.resolve(cls)


@dataclass(frozen=True, slots=True)
class _Setup:
    mediator: Mediator
    resolver: ResolverFactory


def setup_mediary(
    app: FastAPI, mediator: Mediator, *, resolver: ResolverFactory | None = None
) -> None:
    """Make `mediator` the one `MediatorDep` gives the endpoints of `app`.

    For each request or websocket, the endpoint gets a view of `mediator` that resolves
    through `resolver(connection)`, or by default through a `ConnectionResolver` that falls
    back to the mediator's own resolver.
    """

    def default(connection: HTTPConnection) -> Resolver:
        return ConnectionResolver(connection, mediator.resolver)

    app.state.mediary = _Setup(mediator, resolver or default)


def get_mediator(connection: HTTPConnection) -> Mediator:
    """Return the mediator of the connection's app, resolving for this connection.

    It is the dependency behind `MediatorDep`; use it with `Depends` to annotate the
    parameter with another type, such as `Annotated[QuerySender, Depends(get_mediator)]`.

    Raises:
        RuntimeError: `setup_mediary` wasn't called for the app.

    """
    setup = getattr(connection.app.state, "mediary", None)
    if not isinstance(setup, _Setup):
        raise RuntimeError("no mediator for this app; call setup_mediary(app, mediator) first")
    return setup.mediator.with_resolver(setup.resolver(connection))


MediatorDep = Annotated[Mediator, Depends(get_mediator)]
"""An endpoint parameter annotated `MediatorDep` gets the app's mediator for the connection."""
