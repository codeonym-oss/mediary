# FastAPI

The FastAPI integration gives endpoints the app's mediator, without a DI container. Handlers can depend on the current `Request` or `WebSocket`.

```sh
pip install mediary[fastapi]
```

Already using [dishka](dishka.md)? Use its FastAPI integration instead, for request-scoped dependencies.

## Setup

`setup_mediary` attaches a mediator to the app, and endpoints take `MediatorDep`:

```python title="shop/stock.py"
from dataclasses import dataclass

from mediary import Returns, handler, request


@request
@dataclass
class CheckStock(Returns[int]):
    item: str


@handler
async def check_stock(request: CheckStock) -> int:
    return {"book": 3}.get(request.item, 0)
```

<!-- requires: fastapi -->
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mediary import Mediator
from mediary.ext.fastapi import MediatorDep, setup_mediary
from shop.stock import CheckStock

app = FastAPI()
mediator = Mediator()
mediator.scan("shop")
setup_mediary(app, mediator)


@app.get("/stock/{item}")
async def stock(item: str, mediator: MediatorDep) -> int:
    return await mediator.send(CheckStock(item))


client = TestClient(app)  # try it
assert client.get("/stock/book").json() == 3
```

Requests can be Pydantic models, so the request body *is* the message:

<!-- requires: fastapi -->
```python
from pydantic import BaseModel

from mediary import Returns, request


@request
class Restock(BaseModel, Returns[int]):
    item: str
    quantity: int


async def restock(request: Restock) -> int:
    return request.quantity


mediator.register(Restock, restock)


@app.post("/restock")
async def restock_endpoint(command: Restock, mediator: MediatorDep) -> int:
    return await mediator.send(command)


assert client.post("/restock", json={"item": "book", "quantity": 5}).json() == 5
```

## Narrow senders

`MediatorDep` is `Annotated[Mediator, Depends(get_mediator)]`. To give an endpoint a narrower [sender](../guide/cqrs.md#narrow-senders), use `get_mediator` with another type:

<!-- requires: fastapi -->
```python
from typing import Annotated

from fastapi import Depends

from mediary.cqrs import QuerySender
from mediary.ext.fastapi import get_mediator

Queries = Annotated[QuerySender, Depends(get_mediator)]
```

## The current connection

Handlers, behaviors and function dependencies can ask for the current `Request`, `WebSocket` or `HTTPConnection`:

<!-- requires: fastapi -->
```python
from starlette.requests import Request


@request
class WhereAmI(Returns[str]):
    pass


async def where_am_i(query: WhereAmI, connection: Request) -> str:
    return connection.url.path


mediator.register(WhereAmI, where_am_i)


@app.get("/here")
async def here(mediator: MediatorDep) -> str:
    return await mediator.send(WhereAmI())


assert client.get("/here").json() == "/here"
```

Everything else comes from the mediator's own [resolver](../guide/dependency-injection.md).

## Your own resolver per connection

`setup_mediary(app, mediator, resolver=...)` takes a function that makes the resolver for each request or websocket. Wrap the default `ConnectionResolver` to keep the connection available:

<!-- requires: fastapi -->
```python
from dataclasses import dataclass

from starlette.requests import HTTPConnection

from mediary.ext.fastapi import ConnectionResolver


@dataclass
class User:
    name: str


class AuthResolver:
    def __init__(self, connection: HTTPConnection) -> None:
        self.connection = connection
        self.inner = ConnectionResolver(connection, mediator.resolver)

    def resolve(self, cls):
        if cls is User:
            return User(self.connection.headers.get("x-user", "anonymous"))
        return self.inner.resolve(cls)


@request
class WhoAmI(Returns[str]):
    pass


async def who_am_i(query: WhoAmI, user: User) -> str:
    return user.name


mediator.register(WhoAmI, who_am_i)
app = FastAPI()
setup_mediary(app, mediator, resolver=AuthResolver)


@app.get("/me")
async def me(mediator: MediatorDep) -> str:
    return await mediator.send(WhoAmI())


assert TestClient(app).get("/me", headers={"x-user": "ada"}).json() == "ada"
```

Each endpoint gets a [view](../guide/dependency-injection.md#per-request-resolvers) of the mediator that resolves through the connection's resolver, sharing its handlers and behaviors. Endpoints of an app without `setup_mediary` fail with a `RuntimeError` that says so.
