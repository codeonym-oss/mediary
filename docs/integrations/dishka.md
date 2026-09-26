# dishka

[dishka](https://github.com/reagento/dishka) is a DI container for Python with scopes: app-wide dependencies, and ones that live for one request, such as a database session. The integration resolves handlers and their dependencies from it.

```sh
pip install mediary[dishka]
```

## Setup

Add a `MediaryProvider` to your container. It provides:

- every handler and behavior **class** the mediator has, with its constructor dependencies resolved by dishka;
- in each request scope, a **`Mediator`** that resolves from that scope — also provided as `CommandSender`, `QuerySender`, and the mediator's own class.

```{code-block} python
:caption: shop/orders.py
from dataclasses import dataclass

from mediary import Mediator, Returns, handler, request


class Session:
    """A request-scoped dependency, such as a database session."""


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str


@request
@dataclass
class ReserveStock(Returns[Session]):
    item: str


@handler
class PlaceOrderHandler:
    def __init__(self, session: Session, mediator: Mediator) -> None:
        self.session = session
        self.mediator = mediator

    async def handle(self, request: PlaceOrder) -> int:
        reserved_with = await self.mediator.send(ReserveStock(request.item))
        assert reserved_with is self.session  # one session for the whole request
        return 42


@handler
async def reserve_stock(request: ReserveStock, session: Session) -> Session:
    return session
```

<!-- requires: dishka -->
```python
from collections.abc import Iterator

from dishka import Provider, Scope, make_async_container

from mediary import Mediator
from mediary.ext.dishka import MediaryProvider
from shop.orders import PlaceOrder, Session

closed = []


def open_session() -> Iterator[Session]:
    session = Session()
    yield session
    closed.append(session)  # at the end of the request scope


app_provider = Provider()
app_provider.provide(open_session, scope=Scope.REQUEST)

mediator = Mediator()
mediator.scan("shop")  # before making the container: it provides what's registered

container = make_async_container(app_provider, MediaryProvider(mediator))

async with container() as request_container:  # one request
    scoped = await request_container.get(Mediator)
    assert await scoped.send(PlaceOrder("book")) == 42
assert len(closed) == 1

await container.close()
```

Handlers — and the handlers *they* send to — share the request's dependencies: `PlaceOrderHandler` and `reserve_stock` get the same session, closed when the request scope exits.

:::{admonition} Scan first
:class: warning
The provider registers the classes the mediator has when the provider is made. Scan, or register, before making it.
:::

## Lifetimes

- **Transient** handler and behavior classes (the default) are provided in the request scope, uncached: each send gets a new instance, with the scope's dependencies.
- **Singleton** handlers, `@handler(lifetime="singleton")`, are provided once, in `Scope.APP`, so they can only depend on app-scoped dependencies.

Pass `MediaryProvider(mediator, scope=Scope.SESSION)`, say, to provide the scoped mediator and transient classes in another scope.

## Overriding a class

To build a handler your own way, provide its class in a provider listed **after** `MediaryProvider`; dishka uses the last one:

<!-- requires: dishka -->
```python
from shop.orders import PlaceOrderHandler

built = []


def build_handler(session: Session, mediator: Mediator) -> PlaceOrderHandler:
    built.append("by the app")
    return PlaceOrderHandler(session, mediator)


overrides = Provider()
overrides.provide(build_handler, scope=Scope.REQUEST, cache=False)

container = make_async_container(app_provider, MediaryProvider(mediator), overrides)
async with container() as request_container:
    await (await request_container.get(Mediator)).send(PlaceOrder("book"))
assert built == ["by the app"]
await container.close()
```

## With FastAPI

With [dishka's FastAPI integration](https://dishka.readthedocs.io/en/stable/integrations/fastapi.html), endpoints get the request's mediator as `FromDishka[Mediator]` — or a narrower `FromDishka[CommandSender]`:

<!-- requires: dishka,fastapi -->
```python
from dishka.integrations.fastapi import FromDishka, inject, setup_dishka
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


@app.post("/orders/{item}")
@inject
async def place_order(item: str, mediator: FromDishka[Mediator]) -> int:
    return await mediator.send(PlaceOrder(item))


container = make_async_container(app_provider, MediaryProvider(mediator))
setup_dishka(container, app)

with TestClient(app) as client:  # try it
    assert client.post("/orders/book").json() == 42
```

You don't need `mediary[fastapi]` for this: dishka's integration does the work.

## Sync containers

`MediaryProvider` needs an async container, from `make_async_container`. With a sync one, resolve through a `DishkaResolver` yourself — `mediator.with_resolver(DishkaResolver(request_container))` — and provide handler classes as usual.
