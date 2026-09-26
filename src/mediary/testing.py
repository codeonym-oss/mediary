"""Test helpers: a mediator that records what it sends and publishes, with stubbed responses.

`RecordingMediator` is a `Mediator`, so the code under test uses it unchanged. Like any new
mediator it starts empty and isolated: nothing is scanned, and nothing is shared with other
mediators, so each test registers only what it needs. With mediary installed, pytest provides
a fresh one as the `mediator` fixture.

Example:
    async def test_registering_welcomes_the_user(mediator: RecordingMediator) -> None:
        mediator.register(Register, register_user)
        mediator.stub(GetPlan, Plan.FREE)

        await mediator.send(Register("ada@example.com"))

        assert mediator.published_of(Welcomed) == [Welcomed("ada@example.com")]

"""

from typing import TYPE_CHECKING, Any, TypeVar, overload

from ._markers import Returns
from ._mediator import Mediator
from ._publishing import PublishStrategy
from ._resolving import Resolver

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["RecordingMediator"]

_T = TypeVar("_T")
_R = TypeVar("_R")


class RecordingMediator(Mediator):
    """A `Mediator` that records every message, and can answer requests without a handler.

    `sent` and `published` list the messages in the order they were sent or published,
    including those sent by handlers, and including ones that failed. A stubbed request
    type is answered by its stub in place of a handler; behaviors still wrap it.
    """

    def __init__(
        self,
        *,
        resolver: Resolver | None = None,
        publish_strategy: PublishStrategy | None = None,
    ) -> None:
        """Create an empty mediator; the arguments are those of `Mediator`."""
        super().__init__(resolver=resolver, publish_strategy=publish_strategy)
        self.sent: list[object] = []
        self.published: list[object] = []
        self._stubs: dict[type, Callable[[], Awaitable[Any]]] = {}

    @overload
    def stub(self, request_type: type[Returns[_R]], result: _R, /) -> None: ...
    @overload
    def stub(self, request_type: type[object], result: Any, /) -> None: ...
    @overload
    def stub(self, request_type: type[object], /, *, raises: Exception) -> None: ...
    def stub(
        self, request_type: type[object], result: Any = None, /, *, raises: Exception | None = None
    ) -> None:
        """Answer every `request_type` sent with `result`, or fail it with `raises`.

        The stub stands in for the handler: one registered for `request_type` isn't called.
        Stubbing a type again replaces its stub.
        """

        async def answer() -> Any:
            if raises is not None:
                raise raises
            return result

        self._stubs[request_type] = answer

    @overload
    async def send(self, request: Returns[_R], /) -> _R: ...
    @overload
    async def send(self, request: object, /) -> Any: ...
    async def send(self, request: object, /) -> Any:
        """Record `request`, then answer it with its stub or send it to its handler."""
        self.sent.append(request)
        stub = self._stubs.get(type(request))
        if stub is None:
            return await super().send(request)
        return await self._through_pipeline(request, stub)

    async def publish(
        self, notification: object, /, *, strategy: PublishStrategy | None = None
    ) -> None:
        """Record `notification`, then publish it to its handlers."""
        self.published.append(notification)
        await super().publish(notification, strategy=strategy)

    def sent_of(self, request_type: type[_T]) -> list[_T]:
        """Return the sent requests of exactly `request_type`, in order."""
        return [r for r in self.sent if type(r) is request_type]

    def published_of(self, notification_type: type[_T]) -> list[_T]:
        """Return the published notifications of exactly `notification_type`, in order."""
        return [n for n in self.published if type(n) is notification_type]
