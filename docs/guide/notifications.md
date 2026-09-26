# Notifications

A **notification** announces that something happened. Unlike a request, it goes to every one of its handlers — zero, one or many — and returns nothing. The code that publishes it doesn't know, or care, who listens.

## Publishing

Decorate the notification class with `@notification`, and write handlers for it as for requests:

```python title="shop/events.py"
from dataclasses import dataclass

from mediary import handler, notification

sent = []


@notification
@dataclass
class OrderPlaced:
    order_id: int


@handler
async def email_customer(event: OrderPlaced) -> None:
    sent.append(f"email: order {event.order_id} confirmed")


@handler
async def update_stats(event: OrderPlaced) -> None:
    sent.append("stats updated")
```

```python
from mediary import Mediator
from shop.events import OrderPlaced, sent

mediator = Mediator()
mediator.scan("shop")

await mediator.publish(OrderPlaced(42))
assert sent == ["email: order 42 confirmed", "stats updated"]
```

Handlers run in order of their fully qualified names, so the order is the same on every run. Publishing a notification that has no handlers does nothing.

## Publish strategies

A **publish strategy** runs a notification's handlers. Two ship with mediary:

- **`Sequential()`**, the default, runs them one after another. The first error stops the rest and propagates.
- **`Concurrent()`** runs them all at once, in an `asyncio.TaskGroup`. Every handler runs to completion even when some fail; their errors are then raised together, in an `ExceptionGroup`.

Choose one per mediator, or per publish:

```python
from mediary import Concurrent, notification


@notification
class Shutdown:
    pass


async def close_database(event: Shutdown) -> None:
    raise ConnectionError("already closed")


async def flush_logs(event: Shutdown) -> None:
    sent.append("logs flushed")


mediator = Mediator(publish_strategy=Concurrent())
mediator.register(Shutdown, close_database)
mediator.register(Shutdown, flush_logs)

try:
    await mediator.publish(Shutdown())
except ExceptionGroup as group:
    failures = group.exceptions
assert [type(error) for error in failures] == [ConnectionError]
assert sent[-1] == "logs flushed"  # ran despite the other handler failing
```

`await mediator.publish(event, strategy=Sequential())` overrides the mediator's strategy for one publish.

## Your own strategy

A `PublishStrategy` has one method, `publish(handlers)`, which gets each handler as a no-argument async callable. Here is one that logs failures and carries on:

```python
import logging
from collections.abc import Awaitable, Callable, Sequence


class BestEffort:
    async def publish(self, handlers: Sequence[Callable[[], Awaitable[object]]]) -> None:
        for run in handlers:
            try:
                await run()
            except Exception:
                logging.getLogger("events").exception("a handler failed")


mediator = Mediator(publish_strategy=BestEffort())
mediator.register(Shutdown, close_database)
mediator.register(Shutdown, flush_logs)
await mediator.publish(Shutdown())  # logs the ConnectionError, doesn't raise
```

Strategies are also where to hand notifications to a queue or a background task, for handlers that shouldn't delay the publisher.

## Behaviors

[Behaviors](behaviors.md) wrap a publish as a whole: `next()` runs the strategy over every handler. Use `kinds={"notification"}` for behaviors meant only for notifications, or `kinds={"request"}` to keep one off them.

In [CQRS](cqrs.md) terms, notifications are **events**: `@event` is a notification kind of its own.
