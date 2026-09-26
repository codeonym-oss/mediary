# Events after commands

A command often causes events — an order placed, an email changed — that other parts of the app react to. Publishing them from inside the handler has a problem: if the command then fails and its transaction rolls back, the events announced something that never happened.

Instead, handlers **record** events, and a behavior publishes them once the command has succeeded.

```python
from dataclasses import dataclass

from mediary import Mediator, Next, behavior
from mediary.cqrs import Command, command, event


class Events:
    """The events recorded while handling one request."""

    def __init__(self) -> None:
        self.recorded: list[object] = []

    def record(self, event: object) -> None:
        self.recorded.append(event)


@behavior(kinds={"command"}, order=5)  # outside the transaction, if any: publish after commit
class PublishEvents:
    def __init__(self, events: Events, mediator: Mediator) -> None:
        self.events = events
        self.mediator = mediator

    async def handle(self, command: object, next: Next[object]) -> object:
        result = await next()  # if the command fails, nothing is published
        while self.events.recorded:
            await self.mediator.publish(self.events.recorded.pop(0))
        return result


@event
@dataclass
class OrderPlaced:
    order_id: int


@command
@dataclass
class PlaceOrder(Command[int]):
    item: str


async def place_order(command: PlaceOrder, events: Events) -> int:
    if command.item == "unicorn":
        raise ValueError("out of stock")
    events.record(OrderPlaced(42))
    return 42


emails = []


async def email_customer(event: OrderPlaced) -> None:
    emails.append(event.order_id)


class RequestResolver:
    """One `Events` per request, and the mediator that is handling it."""

    def __init__(self, mediator: Mediator) -> None:
        self.events = Events()
        self.mediator = mediator.with_resolver(self)

    def resolve(self, cls):
        if cls is Events:
            return self.events
        if cls is PublishEvents:
            return PublishEvents(self.events, self.mediator)
        return cls()


mediator = Mediator()
mediator.register(PlaceOrder, place_order)
mediator.register(OrderPlaced, email_customer)
mediator.use(PublishEvents)

scope = RequestResolver(mediator)
assert await scope.mediator.send(PlaceOrder("book")) == 42
assert emails == [42]

try:
    await RequestResolver(mediator).mediator.send(PlaceOrder("unicorn"))
except ValueError as error:
    reason = str(error)
assert reason == "out of stock"
assert emails == [42]  # the failed command announced nothing
```

Notes:

- With a [transaction behavior](transactions.md), give `PublishEvents` a lower `order` so it runs outside it, and publishes after the commit.
- Event handlers that send further commands get their events published too: each command runs through the behavior.
- This publishes in-process, after the commit. When events must reach other services even if the process crashes right after the commit, write them to an **outbox** table in the same transaction instead, and publish from there.
