# mediary

Typed, decorator-driven mediator + CQRS for Python — handlers, pipelines and notifications discovered by package scan.

A mediator decouples the code that asks for something from the code that does it. Callers send messages — a request, a command, a query, a notification — and never import their handlers; cross-cutting concerns such as logging, retries, validation and transactions wrap every handler as a pipeline of behaviors.

```{code-block} python
:caption: shop/orders.py
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

```python
from mediary import Mediator
from shop.orders import PlaceOrder

mediator = Mediator()
mediator.scan("shop")  # registers every @handler in the package

order_id = await mediator.send(PlaceOrder("book", 2))  # typed as int
assert order_id == 42
```

## Why mediary

- **Decorate, don't register.** Mark requests with `@request` and handlers with `@handler`; one `mediator.scan("app")` wires the whole package, and reports every wiring mistake at startup.
- **Typed end to end.** `await mediator.send(GetUser(1))` is typed as `User`. Handlers are plain classes or functions, matched structurally: nothing to inherit.
- **Pipelines.** [Behaviors](guide/behaviors.md) wrap handlers like middleware, targeted by type, `Protocol` or kind, and ordered. Logging, retry and timeout ship ready-made, and [OpenTelemetry](integrations/otel.md) tracing as an extra.
- **[Notifications](guide/notifications.md)** to any number of handlers, sequentially or concurrently, and **[streams](guide/streams.md)** of items from async generators.
- **[CQRS](guide/cqrs.md).** `@command`, `@query`, `@event`, and senders that can only send one kind.
- **Pluggable [dependency injection](guide/dependency-injection.md)**, with ready-made [dishka](integrations/dishka.md) and [FastAPI](integrations/fastapi.md) integrations.
- **[Testing](guide/testing.md)** helpers and a pytest fixture.
- **Zero dependencies**, Python 3.11+. Runs on asyncio, or on [trio](integrations/anyio.md) through AnyIO.

## Install

```sh
pip install mediary        # or: uv add mediary
pip install mediary[full]  # with every integration
```

| Extra | Adds |
|---|---|
| `mediary[anyio]` | running on [trio](integrations/anyio.md), through AnyIO |
| `mediary[dishka]` | [dishka](integrations/dishka.md) container integration |
| `mediary[fastapi]` | [FastAPI](integrations/fastapi.md) integration, without a container |
| `mediary[otel]` | [OpenTelemetry](integrations/otel.md) tracing of every message |
| `mediary[full]` | all of the above |

## Next steps

Start with [Getting started](guide/getting-started.md), or jump to the [recipes](recipes/validation.md) for common pipelines. Every example in these docs runs in CI, as written.

```{toctree}
:hidden:
:caption: Guide

guide/getting-started
guide/dependency-injection
guide/behaviors
guide/notifications
guide/streams
guide/cqrs
guide/custom-kinds
guide/testing
```

```{toctree}
:hidden:
:caption: Integrations

dishka <integrations/dishka>
FastAPI <integrations/fastapi>
OpenTelemetry <integrations/otel>
AnyIO and trio <integrations/anyio>
```

```{toctree}
:hidden:
:caption: Recipes

recipes/validation
recipes/transactions
Caching queries <recipes/caching>
Events after commands <recipes/events>
```

```{toctree}
:hidden:
:caption: API reference

reference/mediary
reference/cqrs
reference/kinds
reference/behaviors
reference/testing
reference/ext-dishka
reference/ext-fastapi
reference/ext-otel
```

```{toctree}
:hidden:

changelog
```
