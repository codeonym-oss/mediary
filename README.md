# mediary

[![PyPI](https://img.shields.io/pypi/v/mediary)](https://pypi.org/project/mediary/)
[![Python](https://img.shields.io/pypi/pyversions/mediary)](https://pypi.org/project/mediary/)
[![CI](https://github.com/codeonym-oss/mediary/actions/workflows/ci.yml/badge.svg)](https://github.com/codeonym-oss/mediary/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/codeonym-oss/mediary/blob/main/LICENSE)

Typed, decorator-driven mediator + CQRS for Python — handlers, pipelines and notifications discovered by package scan.

- **Decorate, don't register.** Mark requests with `@request` and handlers with `@handler`; one `mediator.scan("app")` wires the whole package.
- **Typed end to end.** `await mediator.send(GetUser(1))` is typed as `User`; handlers are plain classes or functions, matched structurally.
- **Pipelines.** Behaviors (middleware) wrap handlers, targeted by type, Protocol or kind, and ordered. Logging, retry and timeout ship ready-made.
- **Notifications**, with sequential or concurrent publishing, and **streams** of items from async generators.
- **CQRS pack.** `@command`, `@query`, `@event`, and senders that can only send one kind.
- **Pluggable DI**, with ready-made **dishka** and **FastAPI** integrations as extras.
- **Testing helpers** and a **pytest fixture**. Zero dependencies, asyncio only, Python 3.11+.

## Install

```sh
pip install mediary      # or: uv add mediary
pip install mediary[full]  # with every integration (see Integrations)
```

## Quickstart

Declare a request, what it returns, and its handler:

<!-- file: shop/orders.py -->
```python
from dataclasses import dataclass

from mediary import Returns, handler, request


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str
    quantity: int


@handler
class PlaceOrderHandler:
    async def handle(self, request: PlaceOrder) -> int:
        return 42  # the new order's id
```

Scan the package once at startup, then send requests from anywhere:

```python
from mediary import Mediator
from shop.orders import PlaceOrder

mediator = Mediator()
mediator.scan("shop")  # imports shop and its submodules, registers each @handler

order_id = await mediator.send(PlaceOrder("book", 2))  # typed as int
assert order_id == 42
```

The examples use top-level `await`, as in `python -m asyncio`; in an app they live inside `async def`s. Every example in this README runs in CI.

A handler serves the request its parameter is hinted with, or the one named with `@handler(PlaceOrder)`. Each request has exactly one handler. Scanning is all or nothing: it reports every problem it finds — a missing hint, a duplicate handler, a module that fails to import — in one `ScanError`, and registers nothing.

Prefer explicit wiring? `mediator.register(PlaceOrder, PlaceOrderHandler)` does the same for one handler, and never needs a decorator.

## Function handlers and dependency injection

A handler can be an async function. Its parameters after the request are dependencies, resolved by type hint on every call:

<!-- file: shop/stock.py -->
```python
from dataclasses import dataclass

from mediary import Returns, handler, request


class Inventory:
    def __init__(self) -> None:
        self.counts = {"book": 3}


@request
@dataclass
class CheckStock(Returns[int]):
    item: str


@handler
async def check_stock(request: CheckStock, inventory: Inventory) -> int:
    return inventory.counts.get(request.item, 0)
```

Handler classes and dependencies come from the mediator's resolver, which calls `cls()` by default. Plug in any DI container by adapting it to one method, `resolve(cls)`, which may be sync or async:

```python
from shop.stock import CheckStock, Inventory


class ContainerResolver:
    def __init__(self) -> None:
        self.singletons = {Inventory: Inventory()}

    def resolve(self, cls):
        return self.singletons.get(cls) or cls()


mediator = Mediator(resolver=ContainerResolver())
mediator.scan("shop")
assert await mediator.send(CheckStock("book")) == 3
```

A class handler is resolved for every send, unless it is decorated `@handler(lifetime="singleton")`.

## Behaviors

Behaviors wrap handlers like middleware: each gets the message and `next`, and can act before and after it, change the result, or skip the handler.

```python
from mediary import Next, behavior

calls = []


@behavior(order=-10)  # lower orders run further out
async def trace(request: object, next: Next[object]) -> object:
    calls.append(f"-> {type(request).__name__}")
    result = await next()
    calls.append(f"<- {result}")
    return result


@behavior
async def double_orders(request: PlaceOrder, next: Next[int]) -> int:
    return 2 * await next()


mediator = Mediator()
mediator.scan("shop")
mediator.use(trace)  # scan finds decorated behaviors too; `use` adds them by hand
mediator.use(double_orders)

assert await mediator.send(PlaceOrder("book", 1)) == 84
assert await mediator.send(CheckStock("book")) == 3  # double_orders only wraps PlaceOrder
assert calls == ["-> PlaceOrder", "<- 84", "-> CheckStock", "<- 3"]
```

The hint on the request parameter picks what a behavior wraps: `object` for everything, a class for it and its subclasses, a `Protocol` for every request with those members, or a union. `kinds={"request"}` narrows it to kinds of message, and lower `order`s run further out (ties are broken by name).

Three ready-made behaviors cover production basics. They are never scanned; add them configured:

```python
from mediary.behaviors import LoggingBehavior, RetryBehavior, TimeoutBehavior

mediator.use(LoggingBehavior(), order=-100)  # start, completion, failure, slowness
mediator.use(TimeoutBehavior(seconds=5), order=-50)  # HandlerTimeout when it's too slow
mediator.use(RetryBehavior(max_retries=3), kinds={"request"})  # backoff with jitter
```

`RetryBehavior` retries only transient errors — those whose class is marked `@retryable`, like every `TransientError` — so a bug never runs twice:

```python
from mediary import TransientError, retryable


class GatewayUnavailable(TransientError):  # retried
    pass


@retryable
class StorageError(Exception):  # retried, and so are its subclasses
    pass


class CardDeclined(Exception):  # fails at once
    pass
```

Errors you can't decorate, such as `ConnectionError`, can be listed: `RetryBehavior(retry_on=(ConnectionError,))`.

## Notifications

A notification goes to every one of its handlers — zero or more — in order of their names:

```python
from dataclasses import dataclass

from mediary import Concurrent, notification


@notification
@dataclass
class OrderPlaced:
    order_id: int


emails = []


async def email_customer(event: OrderPlaced) -> None:
    emails.append(f"order {event.order_id} confirmed")


async def update_stats(event: OrderPlaced) -> None:
    pass


mediator = Mediator()
mediator.register(OrderPlaced, email_customer)
mediator.register(OrderPlaced, update_stats)

await mediator.publish(OrderPlaced(42))  # one handler after the other
await mediator.publish(OrderPlaced(42), strategy=Concurrent())  # all at once
assert emails == ["order 42 confirmed"] * 2
```

`Concurrent` runs every handler even when some fail, then raises their errors together in an `ExceptionGroup`. Pass `Mediator(publish_strategy=...)` to change the default, or write your own strategy.

## Streams

A stream request's handler is an async generator: it yields items one by one, and the caller consumes them as they come, with backpressure:

```python
from collections.abc import AsyncIterator

from mediary import NextStream, Yields, stream_request


@stream_request
@dataclass
class ExportOrders(Yields[int]):
    count: int


async def export_orders(request: ExportOrders) -> AsyncIterator[int]:
    for order_id in range(1, request.count + 1):
        yield order_id  # e.g. rows from a database cursor


@behavior
async def skip_odd(request: ExportOrders, next: NextStream[int]) -> AsyncIterator[int]:
    async for order_id in next():
        if order_id % 2 == 0:
            yield order_id


mediator = Mediator()
mediator.register(ExportOrders, export_orders)
mediator.use(skip_odd)

exported = []
async with mediator.stream(ExportOrders(100)) as orders:  # typed as Stream[int]
    async for order_id in orders:
        if order_id > 4:
            break  # the handler and behaviors are closed as the block exits
        exported.append(order_id)
assert exported == [2, 4]
```

Nothing runs until the stream is iterated. Behaviors that are async generators wrap streams, and get the rest of the pipeline from `next()`; other behaviors never do. Plain `async for` works too, but only `async with` (or `aclose()`) closes the pipeline as soon as you stop, rather than whenever the stream is garbage-collected. Cancelling the consumer cancels the handler where it is waiting.

## CQRS

`mediary.cqrs` speaks the language of CQRS: commands change state, queries read it, and events announce what happened.

```python
from dataclasses import dataclass

from mediary.cqrs import Command, Query, QuerySender, command, query

names = {}


@command
@dataclass
class RenameUser(Command[None]):
    user_id: int
    name: str


@query
@dataclass
class GetUserName(Query[str]):
    user_id: int


async def rename_user(command: RenameUser) -> None:
    names[command.user_id] = command.name


async def get_user_name(query: GetUserName) -> str:
    return names[query.user_id]


mediator = Mediator()
mediator.register(RenameUser, rename_user)
mediator.register(GetUserName, get_user_name)


async def profile_page(queries: QuerySender, user_id: int) -> str:
    # A QuerySender can't send commands: type checkers reject `queries.send(RenameUser(...))`.
    return f"<h1>{await queries.send(GetUserName(user_id))}</h1>"


await mediator.send(RenameUser(1, "Ada"))
assert await profile_page(mediator, 1) == "<h1>Ada</h1>"
```

Each command and query has exactly one handler, and a query handler annotated to return `None` is rejected. Behaviors can target `kinds={"command"}`, `{"query"}` or `{"event"}`.

The pack is built only on the public `mediary.kinds` API, which you can use to define kinds of your own, with rules their handlers must follow:

```python
from mediary import Returns
from mediary.kinds import HandlerInfo, define_kind


def returns_something(info: HandlerInfo) -> str | None:
    if info.returns is type(None):
        return "a report must return its rows"
    return None


report = define_kind("report", dispatch="send", rules=[returns_something])


@report
class SalesByMonth(Returns[list[int]]):
    pass
```

## Testing

`mediary.testing.RecordingMediator` is a `Mediator` that records what it sends and publishes, and can answer requests with stubs. With mediary installed, pytest provides a fresh one as the `mediator` fixture:

```python
from mediary.testing import RecordingMediator


async def place_and_announce(mediator: Mediator, item: str) -> None:
    order_id = await mediator.send(PlaceOrder(item, 1))
    await mediator.publish(OrderPlaced(order_id))


async def test_placing_an_order_announces_it(mediator: RecordingMediator) -> None:
    mediator.stub(PlaceOrder, 7)

    await place_and_announce(mediator, "book")

    assert mediator.sent_of(PlaceOrder) == [PlaceOrder("book", 1)]
    assert mediator.published_of(OrderPlaced) == [OrderPlaced(7)]
```

Stubs stand in for handlers — `mediator.stub(PlaceOrder, raises=CardDeclined())` fails instead, and `mediator.stub(ExportOrders, [2, 4])` yields those items — and behaviors still wrap them. Streams are recorded in `mediator.streamed`. Every mediator is isolated, so tests never share registrations.

## Integrations

Extras plug mediary into DI containers and web frameworks; `pip install mediary[full]` installs them all. Each builds on `mediator.with_resolver(resolver)`, a cheap view of a mediator that shares its handlers and behaviors but resolves through another resolver — one per web request, say.

**dishka** (`mediary[dishka]`): `MediaryProvider` provides the mediator's handler classes to [dishka](https://github.com/reagento/dishka), and in each request scope a `Mediator` that resolves from it. Handlers then get request-scoped dependencies, such as one database session per request:

<!-- requires: dishka -->
```python
from dishka import Provider, Scope, make_async_container

from mediary.ext.dishka import MediaryProvider

app_provider = Provider(scope=Scope.REQUEST)
app_provider.provide(Inventory)

mediator = Mediator()
mediator.scan("shop")  # scan before making the container: it provides what's registered

container = make_async_container(app_provider, MediaryProvider(mediator))
async with container() as request_container:
    scoped = await request_container.get(Mediator)
    assert await scoped.send(CheckStock("book")) == 3
await container.close()
```

With dishka's own FastAPI integration, endpoints then take `mediator: FromDishka[Mediator]`.

**FastAPI** (`mediary[fastapi]`), without a container: `setup_mediary` attaches the mediator to the app, and endpoints take `MediatorDep`. Handlers can depend on the current `Request` or `WebSocket`:

<!-- requires: fastapi -->
```python
from fastapi import FastAPI

from mediary.ext.fastapi import MediatorDep, setup_mediary

app = FastAPI()
mediator = Mediator()
mediator.scan("shop")
setup_mediary(app, mediator)


@app.get("/stock/{item}")
async def stock(item: str, mediator: MediatorDep) -> int:
    return await mediator.send(CheckStock(item))


from fastapi.testclient import TestClient  # try it

assert TestClient(app).get("/stock/book").json() == 3
```

## Why not register by hand?

Most mediator libraries have you register each request with its handler, and each pipeline step, in one central place that every feature has to edit. With mediary:

| | Manual registration | mediary |
|---|---|---|
| Adding a feature | write the handler, then edit the registry | write the handler |
| Wiring mistakes | found at the first send | found at startup, all together, by `scan` |
| Handler shape | inherit a base class | any class or function, checked structurally |
| Middleware scope | runs for everything, filters itself | declares what it wraps by type, Protocol or kind |

`register` and `use` are still there when you want explicit wiring, as in libraries and tests.

## Development

Requires [uv](https://docs.astral.sh/uv/). See [CONTRIBUTING.md](https://github.com/codeonym-oss/mediary/blob/main/CONTRIBUTING.md) for the conventions.

```sh
uv sync                        # create .venv with dev tools
uv run pre-commit install      # lint, format and typecheck on commit
uv run pytest                  # tests + coverage gate (95%)
uv run pyright                 # strict type checking
```

## License

[MIT](https://github.com/codeonym-oss/mediary/blob/main/LICENSE)
