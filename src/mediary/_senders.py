"""The narrow views of a mediator that code can depend on: ``Sender`` and ``Publisher``."""

from typing import Any, Protocol, TypeVar, overload

from ._markers import Returns, Yields
from ._streaming import Stream

_R = TypeVar("_R")


class Sender(Protocol):
    """Something that sends requests and streams stream requests, such as a ``Mediator``.

    Depend on it rather than on ``Mediator`` where code only sends, so that a test can pass a
    fake with just these methods.

    Example:
        .. code-block:: python

            async def show_user(sender: Sender, user_id: int) -> User:
                return await sender.send(GetUser(user_id))

    """

    @overload
    async def send(self, request: Returns[_R], /) -> _R: ...
    @overload
    async def send(self, request: object, /) -> Any: ...
    async def send(self, request: object, /) -> Any:
        """Send ``request`` to its handler and return the result."""
        ...

    @overload
    def stream(self, request: Yields[_R], /) -> Stream[_R]: ...
    @overload
    def stream(self, request: object, /) -> Stream[Any]: ...
    def stream(self, request: object, /) -> Stream[Any]:
        """Stream the items ``request``'s handler yields."""
        ...


class Publisher(Protocol):
    """Something that publishes notifications, such as a ``Mediator``.

    Example:
        .. code-block:: python

            async def rename(publisher: Publisher, user: User, name: str) -> None:
                user.name = name
                await publisher.publish(UserRenamed(user.id, name))

    """

    async def publish(self, notification: object, /) -> None:
        """Publish ``notification`` to all of its handlers."""
        ...
