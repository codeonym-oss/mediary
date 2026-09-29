from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from mediary import (
    Concurrent,
    Mediator,
    Returns,
    Stream,
    Yields,
    notification,
    request,
    stream_request,
)
from mediary.cqrs import command
from mediary.ext.otel import TracingBehavior


@request
@dataclass(frozen=True)
class GetUser(Returns[str]):
    user_id: int


@command
@dataclass(frozen=True)
class PlaceOrder(Returns[int]):
    item: str


@notification
@dataclass(frozen=True)
class OrderPlaced:
    order_id: int


@stream_request
@dataclass(frozen=True)
class ExportOrders(Yields[int]):
    count: int


@request
class Fail(Returns[None]):
    pass


@stream_request
class FailMidway(Yields[int]):
    pass


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> Iterator[TracerProvider]:
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider
    provider.shutdown()


@pytest.fixture
def mediator(provider: TracerProvider) -> Mediator:
    m = Mediator()

    async def get_user(request: GetUser) -> str:
        return "ada"

    async def place_order(request: PlaceOrder) -> int:
        await m.send(GetUser(1))  # a nested send
        await m.publish(OrderPlaced(7), strategy=Concurrent())
        return 7

    async def email(event: OrderPlaced) -> None:
        pass

    def audit(event: OrderPlaced) -> None:  # sync, on a worker thread
        pass

    async def export_orders(request: ExportOrders) -> AsyncIterator[int]:
        for n in range(request.count):
            await m.send(GetUser(n))  # nested under the stream's span
            yield n

    async def fail(request: Fail) -> None:
        raise ValueError("boom")

    async def fail_midway(request: FailMidway) -> AsyncIterator[int]:
        yield 1
        raise ConnectionError("lost the cursor")

    m.register(GetUser, get_user)
    m.register(PlaceOrder, place_order)
    m.register(OrderPlaced, email)
    m.register(OrderPlaced, audit)
    m.register(ExportOrders, export_orders)
    m.register(Fail, fail)
    m.register(FailMidway, fail_midway)
    m.use(TracingBehavior(provider))
    return m


def spans(exporter: InMemorySpanExporter) -> dict[str, ReadableSpan]:
    finished = exporter.get_finished_spans()
    by_name = {span.name: span for span in finished}
    assert len(by_name) == len(finished), "one span per message"
    return by_name


def parent_of(span: ReadableSpan) -> int | None:
    return span.parent.span_id if span.parent is not None else None


def span_id(span: ReadableSpan) -> int:
    assert span.context is not None
    return span.context.span_id


async def test_send_opens_one_span_named_after_the_message(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    assert await mediator.send(GetUser(1)) == "ada"
    (span,) = exporter.get_finished_spans()
    assert span.name == "GetUser"
    assert span.attributes == {
        "mediary.message.type": "test_ext_otel.GetUser",
        "mediary.message.kind": "request",
        "mediary.dispatch": "send",
    }
    assert span.status.status_code is StatusCode.UNSET
    assert span.parent is None


async def test_nested_sends_and_publishes_form_a_tree(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    assert await mediator.send(PlaceOrder("book")) == 7
    found = spans(exporter)
    assert set(found) == {"PlaceOrder", "GetUser", "OrderPlaced"}
    assert found["PlaceOrder"].attributes is not None
    assert found["PlaceOrder"].attributes["mediary.message.kind"] == "command"
    assert found["OrderPlaced"].attributes is not None
    assert found["OrderPlaced"].attributes["mediary.dispatch"] == "publish"
    assert parent_of(found["GetUser"]) == span_id(found["PlaceOrder"])
    assert parent_of(found["OrderPlaced"]) == span_id(found["PlaceOrder"])


async def test_a_span_nests_under_the_callers_span(
    mediator: Mediator, exporter: InMemorySpanExporter, provider: TracerProvider
) -> None:
    with provider.get_tracer("app").start_as_current_span("endpoint"):
        await mediator.send(GetUser(1))
    found = spans(exporter)
    assert parent_of(found["GetUser"]) == span_id(found["endpoint"])


async def test_errors_are_recorded_and_propagate(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    with pytest.raises(ValueError, match="boom"):
        await mediator.send(Fail())
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert [event.name for event in span.events] == ["exception"]
    assert span.events[0].attributes is not None
    assert span.events[0].attributes["exception.type"] == "ValueError"


async def test_a_stream_has_one_span_until_it_ends(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    async with mediator.stream(ExportOrders(3)) as orders:
        assert [n async for n in orders] == [0, 1, 2]
    (span,) = [s for s in exporter.get_finished_spans() if s.name == "ExportOrders"]
    assert span.attributes is not None
    assert span.attributes["mediary.dispatch"] == "stream"
    assert span.attributes["mediary.message.kind"] == "stream_request"
    assert span.status.status_code is StatusCode.UNSET
    nested = [s for s in exporter.get_finished_spans() if s.name == "GetUser"]
    assert len(nested) == 3
    assert all(parent_of(s) == span_id(span) for s in nested)


async def test_a_stream_closed_early_ends_its_span(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    stream: Stream[int] = mediator.stream(ExportOrders(100))
    async with stream as orders:
        async for n in orders:
            if n == 1:
                break
        assert not [s for s in exporter.get_finished_spans() if s.name == "ExportOrders"]
    (span,) = [s for s in exporter.get_finished_spans() if s.name == "ExportOrders"]
    assert span.end_time is not None
    assert span.status.status_code is StatusCode.UNSET


async def test_a_stream_error_is_recorded_on_its_span(
    mediator: Mediator, exporter: InMemorySpanExporter
) -> None:
    received: list[int] = []

    async def consume() -> None:
        async with mediator.stream(FailMidway()) as items:
            async for n in items:
                received.append(n)  # noqa: PERF401 - keeps the items before the error

    with pytest.raises(ConnectionError, match="lost the cursor"):
        await consume()
    assert received == [1]
    (span,) = exporter.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert [event.name for event in span.events] == ["exception"]


async def test_the_consumer_runs_outside_the_streams_span(mediator: Mediator) -> None:
    outside = trace.get_current_span()
    async with mediator.stream(ExportOrders(2)) as orders:
        async for _ in orders:
            assert trace.get_current_span() is outside


async def test_without_an_sdk_it_does_nothing() -> None:
    recording: list[bool] = []

    async def get_user(request: GetUser) -> str:
        recording.append(trace.get_current_span().is_recording())
        return "ada"

    m = Mediator()
    m.register(GetUser, get_user)
    # What the global provider is until an SDK sets it (another test's example may have).
    m.use(TracingBehavior(trace.NoOpTracerProvider()))
    assert await m.send(GetUser(1)) == "ada"
    assert recording == [False]
