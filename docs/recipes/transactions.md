# Transactions

Run each command in a transaction that commits when its handler succeeds and rolls back when it fails — without a line of transaction code in the handlers.

The transaction is a request-scoped dependency: the behavior and the handler must share it. Here a small resolver plays the container; with [dishka](../integrations/dishka.md), provide `UnitOfWork` in `Scope.REQUEST` instead.

```python
from dataclasses import dataclass

from mediary import Mediator, Next, behavior
from mediary.cqrs import Command, command


class UnitOfWork:
    """Stands in for a database session with a transaction."""

    def __init__(self) -> None:
        self.pending: list[str] = []
        self.committed: list[str] = []
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed += self.pending
        self.pending = []

    async def rollback(self) -> None:
        self.pending = []
        self.rolled_back = True


@behavior(kinds={"command"}, order=10)  # innermost: after logging, validation and retries
class Transactional:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def handle(self, command: object, next: Next[object]) -> object:
        try:
            result = await next()
        except BaseException:
            await self.uow.rollback()
            raise
        await self.uow.commit()
        return result


@command
@dataclass
class OpenAccount(Command[None]):
    owner: str


async def open_account(command: OpenAccount, uow: UnitOfWork) -> None:
    uow.pending.append(f"account for {command.owner}")
    if command.owner == "nobody":
        raise ValueError("who?")


class RequestResolver:
    """One unit of work per request, shared by the behavior and the handler."""

    def __init__(self) -> None:
        self.uow = UnitOfWork()

    def resolve(self, cls):
        if cls is UnitOfWork:
            return self.uow
        if cls is Transactional:
            return Transactional(self.uow)
        return cls()


mediator = Mediator()
mediator.register(OpenAccount, open_account)
mediator.use(Transactional)

ok = RequestResolver()
await mediator.with_resolver(ok).send(OpenAccount("ada"))
assert ok.uow.committed == ["account for ada"]

failed = RequestResolver()
try:
    await mediator.with_resolver(failed).send(OpenAccount("nobody"))
except ValueError as error:
    reason = str(error)
assert reason == "who?"
assert failed.uow.committed == [] and failed.uow.rolled_back
```

Notes:

- `kinds={"command"}` keeps queries out of transactions; use `{"request"}` without the CQRS pack.
- A command that sends another command runs through the behavior again. With a shared unit of work, commit only in the outermost one — count the depth on the unit of work — or use your database's savepoints.
- Put `RetryBehavior` **outside** the transaction (a lower `order`), so each attempt gets a fresh one.
