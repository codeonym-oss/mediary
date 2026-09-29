# CQRS

Command–query responsibility segregation splits what changes state from what reads it. `mediary.cqrs` speaks its language:

| | Decorator | Base | Handler | Handlers | Sent with |
|---|---|---|---|---|---|
| **Command** — change state | `@command` | `Command[R]` | `@command_handler` | exactly one | `send` |
| **Query** — read state | `@query` | `Query[R]` | `@query_handler` | exactly one, must return a result | `send` |
| **Event** — announce what happened | `@event` | — | `@event_handler` | any number | `publish` |

It ships with mediary; nothing extra to install.

## Commands, queries and events

```{code-block} python
:caption: users/model.py
from dataclasses import dataclass

from mediary.cqrs import (
    Command,
    Query,
    command,
    command_handler,
    event,
    event_handler,
    query,
    query_handler,
)

names: dict[int, str] = {}
history: list[str] = []


@command
@dataclass
class RenameUser(Command[None]):
    user_id: int
    name: str


@event
@dataclass
class UserRenamed:
    user_id: int
    name: str


@query
@dataclass
class GetUserName(Query[str]):
    user_id: int


@command_handler
async def rename_user(command: RenameUser) -> None:
    names[command.user_id] = command.name


@query_handler
async def get_user_name(query: GetUserName) -> str:
    return names[query.user_id]


@event_handler
async def record_rename(event: UserRenamed) -> None:
    history.append(f"{event.user_id} is now {event.name}")
```

```python
from mediary import Mediator
from users.model import GetUserName, RenameUser, UserRenamed, history

mediator = Mediator()
mediator.scan("users")

await mediator.send(RenameUser(1, "Ada"))
await mediator.publish(UserRenamed(1, "Ada"))
assert await mediator.send(GetUserName(1)) == "Ada"
assert history == ["1 is now Ada"]
```

Commands and queries are requests, and events notifications, with names of their own: everything in the guide applies to them. A class is one or the other — `@command` on a `Query` subclass raises `TypeError`, and so does `@query` on a `Command`.

## Handlers of each kind

`@command_handler`, `@query_handler` and `@event_handler` work like `@handler` — on functions and classes, sync or async, bare or with a request type or `lifetime` — and check that the message is of their kind. A `@command_handler` bound to a query is rejected when it is registered or scanned, so the mistake shows at startup:

```python
from mediary import RuleViolation
from mediary.cqrs import command_handler


@command_handler
async def misfiled(query: GetUserName) -> str:
    return ""


try:
    Mediator().register(GetUserName, misfiled)
except RuleViolation as error:
    reason = str(error)
assert "handles only @command messages" in reason
```

They are shorthand, not a requirement: a plain `@handler` serves commands, queries and events just as well.

A handler class can also declare what it handles, for type checkers: `CommandHandler[C, R]`, `QueryHandler[Q, R]` and `EventHandler[E]` are the `Handler` protocol with the message bound to a `Command`, a `Query` or an event. `CommandHandler[GetUserName, str]` is a type error, since a query isn't a command:

```python
from mediary.cqrs import QueryHandler, query_handler


@query_handler
class GetUserNameHandler(QueryHandler[GetUserName, str]):
    async def handle(self, query: GetUserName) -> str:
        return names[query.user_id]
```

## Queries must return

A query that returns nothing is a command in disguise. A query handler annotated to return `None` is rejected when it is registered or scanned:

```python
from mediary.cqrs import Query, query


@query
class Ping(Query[None]):
    pass


async def ping(query: Ping) -> None:
    pass


try:
    Mediator().register(Ping, ping)
except RuleViolation as error:
    reason = str(error)
assert "must return" in reason
```

## Narrow senders

Give each piece of code the narrowest sender it needs. `QuerySender` can only send queries, and `CommandSender` only commands; a `Mediator` is both:

```python
from mediary.cqrs import QuerySender


async def profile_page(queries: QuerySender, user_id: int) -> str:
    # Type checkers reject `queries.send(RenameUser(...))`: a read-only view can't write.
    return f"<h1>{await queries.send(GetUserName(user_id))}</h1>"


assert await profile_page(mediator, 1) == "<h1>Ada</h1>"
```

Senders are `Protocol`s, so a fake is a one-method class in tests. The [dishka integration](../integrations/dishka.md) provides the mediator as both.

## Behaviors per kind

Target [behaviors](behaviors.md) at one side: wrap commands in a [transaction](../recipes/transactions.md), [cache](../recipes/caching.md) queries, retry only queries. `@command_behavior`, `@query_behavior` and `@event_behavior` are `@behavior(kinds={"command"})` and its counterparts, with the same `order`:

```python
from typing import Any

from mediary import Next
from mediary.behaviors import RetryBehavior
from mediary.cqrs import command_behavior

audit = []


@command_behavior(order=-10)
async def audit_commands(command: object, next: Next[Any]) -> Any:
    audit.append(type(command).__name__)
    return await next()


mediator.use(audit_commands)
mediator.use(RetryBehavior(max_retries=2), kinds={"query"})  # reads are safe to repeat

await mediator.send(RenameUser(1, "Grace"))
assert await mediator.send(GetUserName(1)) == "Grace"
assert audit == ["RenameUser"]
```

Ready-made behaviors, such as `RetryBehavior`, take `kinds=` when they are added with `use`.

For events that should follow a command — published once it succeeds — see [events after commands](../recipes/events.md).

The pack is built only on the public [`mediary.kinds`](custom-kinds.md) API, so you can build your own vocabulary the same way.
