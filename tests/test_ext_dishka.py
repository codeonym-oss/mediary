from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest

pytest.importorskip("dishka")

from dishka import Provider, Scope, make_async_container, make_container

from mediary import Mediator, Next, Publisher, Returns, Sender, handler, notification, request
from mediary.cqrs import CommandSender, QuerySender
from mediary.ext.dishka import DishkaResolver, MediaryProvider
from mediary.testing import RecordingMediator


class Session:
    """A request-scoped dependency, such as a database session."""

    opened: list["Session"] = []  # noqa: RUF012
    closed: list["Session"] = []  # noqa: RUF012

    def __init__(self) -> None:
        Session.opened.append(self)


def open_session() -> Iterator[Session]:
    session = Session()
    yield session
    Session.closed.append(session)


def AppProvider() -> Provider:  # noqa: N802
    provider = Provider()
    provider.provide(open_session, scope=Scope.REQUEST)
    return provider


@pytest.fixture(autouse=True)
def reset_sessions() -> None:
    Session.opened, Session.closed = [], []


@request
@dataclass(frozen=True)
class WhichSession(Returns[tuple[Session, Session]]):
    pass


@request
@dataclass(frozen=True)
class SessionOf(Returns[Session]):
    pass


async def session_of(request: SessionOf, session: Session) -> Session:
    return session


class WhichSessionHandler:
    """Returns the session it got, and the one a nested send got, in the same scope."""

    def __init__(self, session: Session, mediator: Mediator) -> None:
        self.session = session
        self.mediator = mediator

    async def handle(self, request: WhichSession) -> tuple[Session, Session]:
        return self.session, await self.mediator.send(SessionOf())


def mediary(mediator: Mediator | None = None) -> tuple[Mediator, Any]:
    mediator = mediator or Mediator()
    mediator.register(WhichSession, WhichSessionHandler)
    mediator.register(SessionOf, session_of)
    return mediator, make_async_container(AppProvider(), MediaryProvider(mediator))


async def test_handlers_get_the_dependencies_of_their_scope() -> None:
    _, container = mediary()
    async with container() as first:
        scoped = await first.get(Mediator)
        own, nested = await scoped.send(WhichSession())
        assert own is nested
        assert Session.closed == []
    async with container() as second:
        own_again, _ = await (await second.get(Mediator)).send(WhichSession())
    assert own_again is not own
    assert Session.closed == Session.opened == [own, own_again]
    await container.close()


async def test_a_scope_provides_the_mediator_as_each_of_its_types() -> None:
    recording = RecordingMediator()
    _, container = mediary(recording)
    async with container() as scope:
        scoped = await scope.get(Mediator)
        assert scoped is not recording
        assert isinstance(scoped.resolver, DishkaResolver)
        assert scoped.resolver.container is scope
        for other in (RecordingMediator, Sender, Publisher, CommandSender, QuerySender):
            assert await scope.get(other) is scoped
        await scoped.send(SessionOf())
    assert recording.sent_of(SessionOf) == [SessionOf()]
    await container.close()


async def test_transient_handlers_are_new_per_send_and_singletons_are_shared() -> None:
    @request
    class Identify(Returns[object]):
        pass

    @handler
    class Transient:
        async def handle(self, request: Identify) -> object:
            return self

    @request
    class IdentifyOnce(Returns[object]):
        pass

    @handler(lifetime="singleton")
    class Singleton:
        async def handle(self, request: IdentifyOnce) -> object:
            return self

    mediator = Mediator()
    mediator.register(Identify, Transient)
    mediator.register(IdentifyOnce, Singleton)
    container = make_async_container(MediaryProvider(mediator))
    seen: list[object] = []
    for _ in range(2):
        async with container() as scope:
            scoped = await scope.get(Mediator)
            seen += [await scoped.send(Identify()), await scoped.send(Identify())]
            seen.append(await scoped.send(IdentifyOnce()))
    transients = [seen[0], seen[1], seen[3], seen[4]]
    assert len({id(t) for t in transients}) == 4
    assert seen[2] is seen[5]
    await container.close()


async def test_behavior_classes_are_resolved_by_dishka() -> None:
    class Tagging:
        def __init__(self, session: Session) -> None:
            self.session = session

        async def handle(self, request: SessionOf, next: Next[Session]) -> Session:
            assert await next() is self.session
            return self.session

    mediator, container = mediary()
    mediator.use(Tagging)
    container = make_async_container(AppProvider(), MediaryProvider(mediator))
    async with container() as scope:
        assert await (await scope.get(Mediator)).send(SessionOf()) is Session.opened[0]
    await container.close()


async def test_notification_handler_classes_are_resolved_by_dishka() -> None:
    @notification
    class Ordered:
        pass

    class Audit:
        sessions: list[Session] = []  # noqa: RUF012

        def __init__(self, session: Session) -> None:
            self.session = session

        async def handle(self, event: Ordered) -> None:
            Audit.sessions.append(self.session)

    mediator, _ = mediary()
    mediator.register(Ordered, Audit)
    container = make_async_container(AppProvider(), MediaryProvider(mediator))
    async with container() as scope:
        await (await scope.get(Mediator)).publish(Ordered())
    assert Audit.sessions == Session.opened
    await container.close()


async def test_classes_can_be_provided_by_the_app_instead() -> None:
    built: list[str] = []

    def build(session: Session, mediator: Mediator) -> WhichSessionHandler:
        built.append("by the app")
        return WhichSessionHandler(session, mediator)

    override = Provider()
    override.provide(build, scope=Scope.REQUEST, cache=False)

    mediator, _ = mediary()
    container = make_async_container(AppProvider(), MediaryProvider(mediator), override)
    async with container() as scope:
        await (await scope.get(Mediator)).send(WhichSession())
    assert built == ["by the app"]
    await container.close()


async def test_the_resolver_works_with_sync_containers_too() -> None:
    mediator = Mediator()
    mediator.register(SessionOf, session_of)
    container = make_container(AppProvider())
    with container() as scope:
        scoped = mediator.with_resolver(DishkaResolver(scope))
        assert await scoped.send(SessionOf()) is Session.opened[0]
    container.close()


async def test_endpoints_get_a_mediator_through_dishkas_fastapi_integration() -> None:
    pytest.importorskip("fastapi")
    from dishka.integrations.fastapi import FromDishka, inject, setup_dishka
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    _, container = mediary()
    app = FastAPI()

    @app.get("/session")
    @inject
    async def endpoint(mediator: FromDishka[Mediator]) -> dict[str, bool]:
        own, nested = await mediator.send(WhichSession())
        return {"same": own is nested}

    setup_dishka(container, app)
    with TestClient(app) as client:
        assert client.get("/session").json() == {"same": True}
        assert client.get("/session").json() == {"same": True}
    assert len(Session.closed) == 2
