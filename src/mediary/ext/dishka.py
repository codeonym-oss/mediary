"""Resolve handlers and their dependencies with dishka: ``pip install mediary[dishka]``.

``MediaryProvider`` provides every handler and behavior class of a mediator to dishka, and in
each scope a ``Mediator`` that resolves from that scope's container. Handlers then get their
dependencies from dishka, including request-scoped ones such as a database session. With
dishka's FastAPI integration, endpoints take one as ``mediator: FromDishka[Mediator]``.

Example:
    .. code-block:: python

        mediator = Mediator()
        mediator.scan("app")  # before making the container, so it provides every handler

        container = make_async_container(AppProvider(), MediaryProvider(mediator))

        async with container() as request_container:  # Scope.REQUEST
            scoped = await request_container.get(Mediator)
            await scoped.send(PlaceOrder("book", 1))

"""

from typing import Any, TypeVar

from dishka import AnyOf, AsyncContainer, BaseScope, Container, Provider, Scope

from .._markers import Lifetime
from .._mediator import Mediator
from .._senders import Publisher, Sender
from ..cqrs import CommandSender, EventPublisher, QuerySender

__all__ = ["DishkaResolver", "MediaryProvider"]

_T = TypeVar("_T")


class DishkaResolver:
    """A ``Resolver`` that gets every type from a dishka container, async or sync.

    Prefer ``MediaryProvider``, which makes one per scope; use this directly to resolve from a
    container of your own, as in ``mediator.with_resolver(DishkaResolver(container))``.
    """

    def __init__(self, container: AsyncContainer | Container) -> None:
        """Resolve from ``container``."""
        self.container = container

    def resolve(self, cls: type[_T], /) -> Any:
        """Return ``container.get(cls)``: an awaitable for an async container."""
        return self.container.get(cls)


class MediaryProvider(Provider):
    """Provides ``mediator``'s handler and behavior classes, and a ``Mediator`` for each scope.

    In ``scope`` (by default ``Scope.REQUEST``), the container provides a view of ``mediator``
    (see ``Mediator.with_resolver``) that resolves from that scope's container, as ``Mediator``,
    ``Sender``, ``Publisher``, ``CommandSender``, ``QuerySender``, ``EventPublisher`` and the
    mediator's own class.

    Handler and behavior classes are provided with their constructor dependencies resolved by
    dishka: transient ones in ``scope`` and uncached, so each send gets a new instance, and
    singleton handlers once, in ``Scope.APP``. Only classes registered before the provider is
    made are provided, so scan first. Provide a class yourself, in a provider listed after
    this one, to override it. It needs an async container (``make_async_container``).
    """

    def __init__(self, mediator: Mediator, *, scope: BaseScope = Scope.REQUEST) -> None:
        """Provide the classes of ``mediator``, and views of it in ``scope``."""
        super().__init__()
        for cls, lifetime in _classes(mediator).items():
            if lifetime == "singleton":
                self.provide(cls, scope=Scope.APP)
            else:
                self.provide(cls, scope=scope, cache=False)

        def scoped(container: AsyncContainer) -> Mediator:
            return mediator.with_resolver(DishkaResolver(container))

        provides = dict.fromkeys(
            [
                Mediator,
                type(mediator),
                Sender,
                Publisher,
                CommandSender,
                QuerySender,
                EventPublisher,
            ]
        )
        self.provide(scoped, scope=scope, provides=AnyOf[tuple(provides)])


def _classes(mediator: Mediator) -> dict[type, Lifetime]:
    """Return the handler and behavior classes ``mediator`` resolves, with their lifetimes.

    Function handlers and behavior instances aren't resolved, so they aren't included.
    """
    registrations = mediator.registrations()
    classes: dict[type, Lifetime] = {
        h.handler: h.lifetime for h in registrations.handlers if isinstance(h.handler, type)
    }
    for b in registrations.behaviors:
        if isinstance(b.behavior, type):
            classes.setdefault(b.behavior, "transient")
    return classes
