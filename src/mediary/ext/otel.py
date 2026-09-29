"""Trace every message with OpenTelemetry: ``pip install mediary[otel]``.

``TracingBehavior`` opens a span around each ``send``, ``publish`` and ``stream``. It needs only
the OpenTelemetry API: until an SDK is configured, its spans do nothing.

Example:
    .. code-block:: python

        from mediary.ext.otel import TracingBehavior

        mediator.use(TracingBehavior(), order=-1000)  # outermost, so the span covers the rest

"""

from collections.abc import AsyncIterator
from typing import TypeVar

try:
    from opentelemetry import trace
except ImportError:
    raise ModuleNotFoundError(
        "mediary.ext.otel needs OpenTelemetry: pip install mediary[otel]", name="opentelemetry"
    ) from None

from .. import Next, NextStream, __version__
from ..kinds import kind_of

__all__ = ["TracingBehavior"]

_T = TypeVar("_T")


class TracingBehavior:
    """Open an OpenTelemetry span around each message sent, published or streamed.

    The span is named after the message's class, and nests under the caller's current span,
    so the spans of messages sent by a handler form a tree under its own. Its attributes are:

    - ``mediary.message.type``: the message's fully qualified class name;
    - ``mediary.message.kind``: its kind, such as "request", "command" or "notification";
    - ``mediary.dispatch``: how it was dispatched: "send", "publish" or "stream".

    An error is recorded on the span, and sets its status to error, before it propagates. The
    span of a stream stays open until the stream ends, fails or is closed.

    Spans come from ``tracer_provider``, or else from the global one, which does nothing until
    an SDK sets it.
    """

    def __init__(self, tracer_provider: trace.TracerProvider | None = None) -> None:
        """Get the tracer the spans come from."""
        self.tracer = trace.get_tracer("mediary", __version__, tracer_provider)

    async def handle(self, message: object, next: Next[_T]) -> _T:
        """Run the rest of the pipeline of a sent or published message in a span."""
        with self.tracer.start_as_current_span(
            type(message).__qualname__, attributes=_attributes(type(message))
        ):
            return await next()

    async def handle_stream(self, message: object, next: NextStream[_T]) -> AsyncIterator[_T]:
        """Yield the items of a stream, producing each one in its span."""
        span = self.tracer.start_span(
            type(message).__qualname__, attributes=_attributes(type(message))
        )
        try:
            items = next()
            while True:
                # The span is current only while an item is being produced: between items, the
                # consumer runs in its own context.
                with trace.use_span(span, record_exception=True, set_status_on_exception=True):
                    try:
                        item = await anext(items)
                    except StopAsyncIteration:
                        return
                yield item
        finally:
            span.end()


def _attributes(message_type: type) -> dict[str, str]:
    kind = kind_of(message_type)
    attributes = {"mediary.message.type": f"{message_type.__module__}.{message_type.__qualname__}"}
    if kind is not None:
        attributes["mediary.message.kind"] = kind.name
        attributes["mediary.dispatch"] = kind.dispatch
    return attributes
