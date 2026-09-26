# CQRS

Command–query responsibility segregation splits what changes state from what reads it. `mediary.cqrs` speaks its language:

| | Decorator | Base | Handlers | Sent with |
|---|---|---|---|---|
| **Command** — change state | `@command` | `Command[R]` | exactly one | `send` |
| **Query** — read state | `@query` | `Query[R]` | exactly one, must return a result | `send` |
| **Event** — announce what happened | `@event` | — | any number | `publish` |

It ships with mediary; nothing extra to install.

## Commands, queries and events

```{code-block} python
:caption: users/model.py
from dataclasses import dataclass

from mediary import handler
from mediary.cqrs import Command, Query, command, event, query

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


@handler
async def rename_user(command: RenameUser) -> None:
    names[command.user_id] = command.name


@handler
async def get_user_name(query: GetUserName) -> str:
    return names[query.user_id]


@handler
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

## Queries must return

A query that returns nothing is a command in disguise. A query handler annotated to return `None` is rejected when it is registered or scanned:

```python
from mediary import RuleViolation
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

Target [behaviors](behaviors.md) at one side with `kinds=`: wrap commands in a [transaction](../recipes/transactions.md), [cache](../recipes/caching.md) queries, retry only queries:

```python
from mediary.behaviors import RetryBehavior

mediator.use(RetryBehavior(max_retries=2), kinds={"query"})  # reads are safe to repeat
```

For events that should follow a command — published once it succeeds — see [events after commands](../recipes/events.md).

The pack is built only on the public [`mediary.kinds`](custom-kinds.md) API, so you can build your own vocabulary the same way.
