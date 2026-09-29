# Behaviors

A **behavior** wraps handlers like middleware. It gets the message and `next`, which runs the rest of the pipeline — inner behaviors, then the handler — and can act before and after it, change its result, or not call it at all. Logging, validation, retries, timeouts, transactions and caching are all behaviors.

## Writing one

A behavior is an async function, or a class with an async `handle`, taking the message and `next`:

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
async def place_order(request: PlaceOrder) -> int:
    return 42


@request
@dataclass
class CheckStock(Returns[int]):
    item: str


@handler
async def check_stock(request: CheckStock) -> int:
    return 3
```

```python
from mediary import Mediator, Next, behavior
from shop.orders import CheckStock, PlaceOrder

calls = []


@behavior(order=-10)  # lower orders run further out
async def trace(message: object, next: Next[object]) -> object:
    calls.append(f"-> {type(message).__name__}")
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

`@behavior` marks it for `scan`; `use` adds one by hand, decorated or not.

## What a behavior wraps

The type hint of the message parameter picks the messages a behavior wraps:

| Hint | Wraps |
|---|---|
| none, `object` or `Any` | every message |
| a class | that class and its subclasses |
| a `Protocol` | every message class that has the protocol's members |
| a union, `A | B` | any of its members |

Then `kinds=` narrows it to kinds of message, by the name of their decorator: `{"request"}`, `{"notification"}`, or the [CQRS](cqrs.md) `{"command"}`, `{"query"}` and `{"event"}`. A name that isn't a defined kind, such as a typo, raises `InvalidBehavior` when the behavior is added or scanned, rather than wrapping nothing.

Protocols make behaviors opt-in by shape, with no base class or registry. Every request with an `idempotency_key` gets deduplicated, say:

```python
from dataclasses import dataclass
from typing import Protocol

from mediary import Returns, request


class Idempotent(Protocol):
    idempotency_key: str


@request
@dataclass
class Charge(Returns[str]):
    amount: int
    idempotency_key: str


async def charge(request: Charge) -> str:
    return f"charged {request.amount}"


done: dict[str, object] = {}


async def deduplicate(request: Idempotent, next: Next[object]) -> object:
    if request.idempotency_key not in done:
        done[request.idempotency_key] = await next()
    return done[request.idempotency_key]


mediator = Mediator()
mediator.register(Charge, charge)
mediator.use(deduplicate)
assert await mediator.send(Charge(10, "k1")) == "charged 10"
assert await mediator.send(Charge(99, "k1")) == "charged 10"  # not charged twice
```

## Order

Behaviors with a lower `order` run further out: they see the message first and the result last. Ties are broken by the behavior's fully qualified name, so the order never depends on import order. Give `order` to `@behavior(order=...)`, or override it in `use(..., order=...)`.

A common layout, outermost first:

| order | behavior |
|---|---|
| -100 | logging |
| -50 | timeout |
| -10 | retry |
| 0 | validation, authorization |
| 10 | transaction |

## Class behaviors and dependencies

A class behavior is resolved through the mediator's [resolver](dependency-injection.md) on every call, so it gets dependencies in `__init__`. A function behavior gets dependencies as parameters after `next`:

```python
import logging


@behavior
class Audit:
    def __init__(self) -> None:
        self.logger = logging.getLogger("audit")

    async def handle(self, request: PlaceOrder, next: Next[int]) -> int:
        order_id = await next()
        self.logger.info("order %s placed", order_id)
        return order_id


mediator = Mediator()
mediator.scan("shop")
mediator.use(Audit)
assert await mediator.send(PlaceOrder("book", 1)) == 42
```

Already-built instances work too: `use` keeps a configured instance, such as `RetryBehavior(max_retries=5)`, and calls it as it is.

## Ready-made behaviors

`mediary.behaviors` ships three production basics. They are never scanned; add them configured:

```python
from mediary.behaviors import LoggingBehavior, RetryBehavior, TimeoutBehavior

mediator.use(LoggingBehavior(), order=-100)  # start, completion, failure, slowness
mediator.use(TimeoutBehavior(seconds=5), order=-50)  # HandlerTimeout when it's too slow
mediator.use(RetryBehavior(max_retries=3), kinds={"request"})  # backoff with jitter
```

- **`LoggingBehavior`** logs each message's start (DEBUG), completion (INFO, or WARNING when slower than `slow_after`) and failure (ERROR, with the traceback), with structured `extra` fields: `mediary_kind`, `mediary_type`, `mediary_payload` and `mediary_duration_ms`. It logs streams too, with the number of items yielded as `mediary_items`, and says when one was closed early.
- **`TimeoutBehavior`** cancels the rest of the pipeline after `seconds`, and raises `HandlerTimeout`.
- **`RetryBehavior`** runs the rest of the pipeline again on transient errors, with exponential backoff and full jitter.

### What gets retried

Retrying a bug only runs it twice, so `RetryBehavior` retries only errors marked transient: those whose class, or a base, is decorated `@retryable`, like every `TransientError`:

```python
from mediary import TransientError, retryable


class GatewayUnavailable(TransientError):  # retried
    pass


@retryable
class StorageError(Exception):  # retried, and so are its subclasses
    pass


class CardDeclined(Exception):  # fails at once
    pass


attempts = []


@request
class Pay(Returns[str]):
    pass


async def pay(request: Pay) -> str:
    attempts.append(len(attempts))
    if len(attempts) < 3:
        raise GatewayUnavailable
    return "paid"


async def no_wait(seconds: float) -> None:
    pass


mediator = Mediator()
mediator.register(Pay, pay)
mediator.use(RetryBehavior(max_retries=3, sleep=no_wait))
assert await mediator.send(Pay()) == "paid"
assert len(attempts) == 3
```

Errors you can't decorate, such as `ConnectionError`, can be listed: `RetryBehavior(retry_on=(ConnectionError,))`. Retry only what is safe to run twice — narrow it with `kinds=`, such as `{"query"}`.

## Behaviors and notifications

Behaviors wrap notifications too: `next()` publishes to all of the notification's handlers. Narrow a behavior with `kinds={"request"}` to keep it off notifications. Streams have [their own behaviors](streams.md#stream-behaviors).
