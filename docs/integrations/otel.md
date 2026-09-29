# OpenTelemetry

The OpenTelemetry integration traces every message: `TracingBehavior` opens a span around each `send`, `publish` and `stream`.

```sh
pip install mediary[otel]
```

The extra installs only the [OpenTelemetry](https://opentelemetry.io/docs/languages/python/) API. Until your app configures an SDK, the spans do nothing and cost next to nothing, so a library can enable tracing and leave exporting to the app.

## Setup

Configure the SDK — here with an exporter that prints each span — then add the behavior once, outermost, so its span covers the other behaviors too:

<!-- requires: opentelemetry.sdk -->
```python
from dataclasses import dataclass

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

from mediary import Mediator, Returns, notification, request
from mediary.ext.otel import TracingBehavior

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)


@request
@dataclass
class GetPrice(Returns[int]):
    item: str


@notification
@dataclass
class OrderPlaced:
    item: str


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str


async def get_price(request: GetPrice) -> int:
    return 12


async def email_receipt(event: OrderPlaced) -> None:
    pass


async def place_order(request: PlaceOrder) -> int:
    price = await mediator.send(GetPrice(request.item))
    await mediator.publish(OrderPlaced(request.item))
    return price


mediator = Mediator()
mediator.register(GetPrice, get_price)
mediator.register(OrderPlaced, email_receipt)
mediator.register(PlaceOrder, place_order)
mediator.use(TracingBehavior(), order=-1000)

assert await mediator.send(PlaceOrder("book")) == 12
```

That prints three spans: `PlaceOrder`, with `GetPrice` and `OrderPlaced` nested under it, since the handler sent and published them. Use your usual exporter, such as OTLP, in place of the console one.

`TracingBehavior(tracer_provider)` takes a provider of its own, to trace without setting the global one.

## What a span records

Each span is named after the message's class, and has these attributes:

| Attribute | Value |
|---|---|
| `mediary.message.type` | the message's fully qualified class name, such as `shop.orders.PlaceOrder` |
| `mediary.message.kind` | its kind: `request`, `notification`, `stream_request`, or a custom one such as `command` |
| `mediary.dispatch` | how it was dispatched: `send`, `publish` or `stream` |

- **Nesting.** A span is a child of the caller's current span — an incoming HTTP request's, say — and the spans of messages a handler sends or publishes are children of its own. This holds across concurrent publishing and [sync handlers](../guide/getting-started.md#sync-handlers) on worker threads.
- **Errors.** An error is recorded on the span as an exception event, and sets its status to error; then it propagates as usual.
- **Streams.** A stream's span opens at the first item and stays open until the stream ends, fails or is closed, so it spans the whole iteration. Messages the handler sends while producing an item nest under it; the consumer's code between items doesn't.
