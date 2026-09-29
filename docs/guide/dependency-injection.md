# Dependency injection

Handlers need things — a database session, a repository, an HTTP client. mediary gets them from the mediator's **resolver**, a one-method seam you can back with any DI container.

## What gets resolved

- **Handler classes** are resolved, then their `handle` is called. Put dependencies in `__init__`.
- **Function handlers** get the request first; every parameter after it is resolved by its type hint, on every call.
- **Behaviors** follow the same rules: [class behaviors](behaviors.md) are resolved, and a function behavior's parameters after `next` are.

```{code-block} python
:caption: shop/stock.py
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


@request
@dataclass
class Restock(Returns[int]):
    item: str
    quantity: int


@handler
class RestockHandler:
    def __init__(self, inventory: Inventory) -> None:
        self.inventory = inventory

    async def handle(self, request: Restock) -> int:
        self.inventory.counts[request.item] += request.quantity
        return self.inventory.counts[request.item]
```

## The default resolver

Without a resolver, mediary calls each type with no arguments: `cls()`. That covers handler classes without dependencies, and function handlers whose dependencies can be built with no arguments:

```python
from mediary import Mediator
from shop.stock import CheckStock

mediator = Mediator()
mediator.scan("shop")
assert await mediator.send(CheckStock("book")) == 3
```

`RestockHandler` needs an `Inventory`, which `cls()` can't give it: it needs a real resolver.

## Your own resolver

A `Resolver` has one method, `resolve(cls)`, which returns an instance of `cls`. It may be sync or async. Adapt your container to it:

```python
from shop.stock import Inventory, Restock, RestockHandler


class AppResolver:
    def __init__(self) -> None:
        self.inventory = Inventory()  # one for the whole app

    def resolve(self, cls):
        if cls is Inventory:
            return self.inventory
        if cls is RestockHandler:
            return RestockHandler(self.inventory)
        return cls()


mediator = Mediator(resolver=AppResolver())
mediator.scan("shop")
assert await mediator.send(Restock("book", 2)) == 5
assert await mediator.send(CheckStock("book")) == 5  # the same inventory
```

With a container, `resolve` is a one-liner such as `return self.container.get(cls)`. For **dishka**, it is ready-made: see the [dishka integration](../integrations/dishka.md).

## Lifetimes

A class handler is resolved for every send, so it can hold per-call state and get fresh dependencies. A handler that is expensive to build, and safe to share, can be resolved once and kept:

```python
from mediary import Returns, handler, request


@request
class CountCalls(Returns[int]):
    pass


@handler(lifetime="singleton")
class CountCallsHandler:
    def __init__(self) -> None:
        self.calls = 0

    async def handle(self, request: CountCalls) -> int:
        self.calls += 1
        return self.calls


mediator = Mediator()
mediator.register(CountCalls, CountCallsHandler)
assert [await mediator.send(CountCalls()) for _ in range(3)] == [1, 2, 3]
```

The lifetime of a dependency is your container's business; mediary only asks it for one on every call.

## Per-request resolvers

Web apps usually scope some dependencies to a request: one database session per HTTP request, shared by every handler that request runs. `with_resolver` gives a view of a mediator that resolves through another resolver — one bound to that scope — while sharing everything else:

```python
from dataclasses import dataclass


@dataclass
class RequestContext:
    request_id: str


class RequestResolver:
    def __init__(self, parent, context: RequestContext) -> None:
        self.parent = parent
        self.context = context

    def resolve(self, cls):
        if cls is RequestContext:
            return self.context
        return self.parent.resolve(cls)


@request
class WhoAmI(Returns[str]):
    pass


async def who_am_i(request: WhoAmI, context: RequestContext) -> str:
    return context.request_id


mediator = Mediator()
mediator.register(WhoAmI, who_am_i)

scoped = mediator.with_resolver(RequestResolver(mediator.resolver, RequestContext("req-1")))
assert await scoped.send(WhoAmI()) == "req-1"
```

The view is cheap to make — make one per unit of work. It shares its handlers, behaviors, publish strategy and singleton handlers with the mediator it came from, both ways. The [dishka](../integrations/dishka.md) and [FastAPI](../integrations/fastapi.md) integrations are built on it.

## Handlers that send

A handler can send other requests: depend on the mediator, or on the narrower `Sender` (`send` and `stream`) or `Publisher` (`publish`), which a `Mediator` is and a test fake can be. Register the mediator with your container (or resolve it in your resolver) so handlers get the one — or the per-request view — that is running them. The [dishka integration](../integrations/dishka.md) does this for you, and provides the mediator as `Mediator`, `Sender`, `Publisher`, `CommandSender` and `QuerySender`.
