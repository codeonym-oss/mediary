# Streams

Some requests answer with many items: rows of an export, pages of search results, tokens from a language model. A **stream request**'s handler is an async generator; the caller consumes the items as they come, with backpressure, instead of waiting for a list of all of them.

## Streaming

Decorate the request with `@stream_request`, declare its items with `Yields[...]`, and `yield` them from the handler:

```python title="shop/exports.py"
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mediary import Yields, handler, stream_request


@stream_request
@dataclass
class ExportOrders(Yields[int]):
    count: int


@handler
async def export_orders(request: ExportOrders) -> AsyncIterator[int]:
    for order_id in range(1, request.count + 1):
        yield order_id  # e.g. rows from a database cursor
```

`mediator.stream(...)` returns a `Stream`, typed from `Yields[...]`:

```python
from mediary import Mediator
from shop.exports import ExportOrders

mediator = Mediator()
mediator.scan("shop")

async with mediator.stream(ExportOrders(3)) as orders:  # a Stream[int]
    assert [order_id async for order_id in orders] == [1, 2, 3]
```

Class handlers work too: their `handle` is the async generator.

## Closing early

Nothing runs until the stream is iterated, and the handler only produces the items the consumer asks for. Stop early and the rest is never produced:

```python
exported = []
async with mediator.stream(ExportOrders(1_000_000)) as orders:
    async for order_id in orders:
        if order_id > 2:
            break  # the handler and behaviors are closed as the block exits
        exported.append(order_id)
assert exported == [1, 2]
```

Iterate inside `async with` (or call `await stream.aclose()`): leaving the block closes the handler at once, running its `finally` blocks and `async with` exits — releasing a database cursor, say. A plain `async for` works, but leaves closing to the garbage collector — which trio can't do, so under trio always use `async with`. Cancelling the consumer cancels the handler where it is waiting.

The handler is looked up when you call `stream`: a request without one raises `HandlerNotFound` there, not on the first item.

## Stream behaviors

Behaviors that are async generators wrap streams. They get the rest of the pipeline from `next()`, as an async iterator, and yield what the caller should see — filtering, transforming, counting, or adding items:

```python
from collections.abc import AsyncIterator

from mediary import NextStream, behavior


@behavior
async def skip_odd(request: ExportOrders, next: NextStream[int]) -> AsyncIterator[int]:
    async for order_id in next():
        if order_id % 2 == 0:
            yield order_id


mediator = Mediator()
mediator.scan("shop")
mediator.use(skip_odd)

async with mediator.stream(ExportOrders(6)) as orders:
    assert [order_id async for order_id in orders] == [2, 4, 6]
```

Stream behaviors wrap only stream requests, and other behaviors never do, so a logging behavior written for `send` doesn't see streams by accident. Hints, `kinds=` and `order` work as for [other behaviors](behaviors.md); the kind of a stream request is `"stream_request"`.

## Errors

An error raised by the handler reaches the consumer at the item where it happened, through every behavior on the way, so a stream behavior can catch it:

```python
from mediary import Yields, stream_request


@stream_request
class Countdown(Yields[int]):
    pass


async def countdown(request: Countdown) -> AsyncIterator[int]:
    yield 2
    yield 1
    raise ConnectionError("lost the cursor")


mediator = Mediator()
mediator.register(Countdown, countdown)

received = []
try:
    async with mediator.stream(Countdown()) as numbers:
        async for number in numbers:
            received.append(number)
except ConnectionError as error:
    reason = str(error)
assert reason == "lost the cursor"
assert received == [2, 1]
```
