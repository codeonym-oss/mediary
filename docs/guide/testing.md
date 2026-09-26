# Testing

Handlers are plain classes and functions: test them by calling them. For code that *uses* the mediator — endpoints, services, handlers that send — `mediary.testing` has `RecordingMediator`.

## The `mediator` fixture

`RecordingMediator` is a `Mediator` that records what it sends, publishes and streams, and can answer requests with stubs. With mediary installed, pytest provides a fresh one to every test that asks for `mediator`:

```{code-block} python
:caption: shop/orders.py
from dataclasses import dataclass

from mediary import Mediator, Returns, notification, request


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str
    quantity: int


@notification
@dataclass
class OrderPlaced:
    order_id: int


async def place_and_announce(mediator: Mediator, item: str) -> int:
    order_id = await mediator.send(PlaceOrder(item, 1))
    await mediator.publish(OrderPlaced(order_id))
    return order_id
```

```python
from mediary.testing import RecordingMediator
from shop.orders import OrderPlaced, PlaceOrder, place_and_announce


async def test_placing_an_order_announces_it(mediator: RecordingMediator) -> None:
    mediator.stub(PlaceOrder, 7)

    assert await place_and_announce(mediator, "book") == 7

    assert mediator.sent_of(PlaceOrder) == [PlaceOrder("book", 1)]
    assert mediator.published_of(OrderPlaced) == [OrderPlaced(7)]
```

Every mediator is isolated — nothing is scanned or shared — so each test registers only what it needs, and tests never leak into each other.

## Recording

| Attribute | Holds |
|---|---|
| `sent` | every request sent, in order |
| `published` | every notification published |
| `streamed` | every stream request streamed |
| `sent_of(T)`, `published_of(T)`, `streamed_of(T)` | those of type `T` only |

Messages are recorded before they are handled, so failed ones are recorded too, and so are those that handlers send.

## Stubs

A stub stands in for a request's handler:

```python
from mediary import Yields, stream_request


class CardDeclined(Exception):
    pass


@stream_request
class ExportOrders(Yields[int]):
    pass


async def test_stubs(mediator: RecordingMediator) -> None:
    mediator.stub(PlaceOrder, 7)  # returns 7
    assert await mediator.send(PlaceOrder("book", 1)) == 7

    mediator.stub(PlaceOrder, raises=CardDeclined())  # raises instead
    try:
        await mediator.send(PlaceOrder("book", 1))
    except CardDeclined as error:
        declined = error
    assert isinstance(declined, CardDeclined)

    mediator.stub(ExportOrders, [2, 4])  # a stream yields the items
    async with mediator.stream(ExportOrders()) as orders:
        assert [order async for order in orders] == [2, 4]
```

Stubs are typed: `stub(PlaceOrder, "seven")` is a type error, as `PlaceOrder` returns an `int`. Behaviors still wrap stubs, so a test can check a behavior against a stubbed handler.

## Real handlers

A `RecordingMediator` runs registered handlers like any mediator, and records all the same. Mix real handlers with stubs to test a slice of the app:

```python
async def place_order(request: PlaceOrder) -> int:
    return 42


async def test_a_real_handler(mediator: RecordingMediator) -> None:
    mediator.register(PlaceOrder, place_order)

    assert await place_and_announce(mediator, "book") == 42
    assert mediator.published_of(OrderPlaced) == [OrderPlaced(42)]
```

## Your own fixture

To register what every test needs, or to pass a resolver, override the fixture in a `conftest.py`:

```python
import pytest


@pytest.fixture
def mediator() -> RecordingMediator:
    mediator = RecordingMediator()
    mediator.register(PlaceOrder, place_order)
    return mediator
```

`RecordingMediator` takes the same arguments as `Mediator`: `resolver=` and `publish_strategy=`.
