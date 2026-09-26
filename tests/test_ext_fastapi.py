from dataclasses import dataclass
from typing import Annotated, Any

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import HTTPConnection

from mediary import Mediator, Returns, request
from mediary.cqrs import Query, QuerySender, query
from mediary.ext.fastapi import ConnectionResolver, MediatorDep, get_mediator, setup_mediary


@request
class PlaceOrder(BaseModel, Returns[int]):
    item: str
    quantity: int


async def place_order(request: PlaceOrder) -> int:
    return 42 if request.item == "book" else 0


@query
@dataclass(frozen=True)
class WhoAsked(Query[str]):
    pass


class Greeting:
    def __init__(self) -> None:
        self.text = "hello"


async def who_asked(request: WhoAsked, connection: HTTPConnection, greeting: Greeting) -> str:
    return f"{greeting.text} {connection.url.path}"


def app_with(mediator: Mediator, **options: Any) -> FastAPI:
    mediator.register(PlaceOrder, place_order)
    mediator.register(WhoAsked, who_asked)
    app = FastAPI()
    setup_mediary(app, mediator, **options)

    @app.post("/orders")
    async def orders(order: PlaceOrder, mediator: MediatorDep) -> int:
        return await mediator.send(order)

    @app.get("/who")
    async def who(queries: Annotated[QuerySender, Depends(get_mediator)]) -> str:
        return await queries.send(WhoAsked())

    @app.websocket("/ws")
    async def ws(websocket: WebSocket, mediator: MediatorDep) -> None:
        await websocket.accept()
        await websocket.send_text(await mediator.send(WhoAsked()))
        await websocket.close()

    return app


def test_endpoints_send_through_the_apps_mediator() -> None:
    with TestClient(app_with(Mediator())) as client:
        assert client.post("/orders", json={"item": "book", "quantity": 2}).json() == 42


def test_handlers_can_depend_on_the_current_request_or_websocket() -> None:
    with TestClient(app_with(Mediator())) as client:
        assert client.get("/who").json() == "hello /who"
        with client.websocket_connect("/ws") as websocket:
            assert websocket.receive_text() == "hello /ws"


def test_each_connection_can_get_its_own_resolver() -> None:
    class Polite:
        def __init__(self, connection: HTTPConnection, fallback: Any) -> None:
            self.inner = ConnectionResolver(connection, fallback)

        def resolve(self, cls: type) -> Any:
            if cls is Greeting:
                greeting = Greeting()
                greeting.text = "good day"
                return greeting
            return self.inner.resolve(cls)

    mediator = Mediator()

    def polite(connection: HTTPConnection) -> Polite:
        return Polite(connection, mediator.resolver)

    app = app_with(mediator, resolver=polite)
    with TestClient(app) as client:
        assert client.get("/who").json() == "good day /who"


def test_the_resolver_only_supplies_the_connection_it_is_given() -> None:
    fallbacks: list[type] = []

    class Fallback:
        def resolve(self, cls: type) -> Any:
            fallbacks.append(cls)
            return None

    connection = HTTPConnection({"type": "websocket", "headers": []})
    resolver = ConnectionResolver(connection, Fallback())
    assert resolver.resolve(HTTPConnection) is connection
    resolver.resolve(Request)
    assert fallbacks == [Request]


def test_the_app_must_be_set_up_first() -> None:
    app = FastAPI()

    @app.get("/")
    async def root(mediator: MediatorDep) -> None:
        pass

    with TestClient(app) as client, pytest.raises(RuntimeError, match="setup_mediary"):
        client.get("/")
