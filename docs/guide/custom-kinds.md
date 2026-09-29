# Custom kinds

`@request`, `@notification`, `@stream_request` and the [CQRS](cqrs.md) decorators are all **kinds** of message. `mediary.kinds` lets you define your own: a decorator, how its messages are dispatched, and rules their handlers must follow. Handlers, behaviors, `scan` and the ready-made behaviors work with every kind.

## Defining a kind

`define_kind` returns the new kind's class decorator:

```python
from dataclasses import dataclass

from mediary import Mediator, Returns
from mediary.kinds import define_kind

job = define_kind("job", dispatch="send")


@job
@dataclass
class ResizeImage(Returns[str]):
    path: str


async def resize_image(job: ResizeImage) -> str:
    return f"{job.path} resized"


mediator = Mediator()
mediator.register(ResizeImage, resize_image)
assert await mediator.send(ResizeImage("cat.png")) == "cat.png resized"
```

`dispatch` says how its messages travel:

| `dispatch` | Handlers | Sent with | Like |
|---|---|---|---|
| `"send"` | exactly one | `send` | `@request`, `@command`, `@query` |
| `"publish"` | any number | `publish` | `@notification`, `@event` |
| `"stream"` | exactly one async generator | `stream` | `@stream_request` |

Behaviors target the kind by name, with `kinds={"job"}`.

Kinds are global, like the classes they decorate: define each one once, at import time, in a module of its own. Defining a name twice raises `ValueError`.

## Rules

A **rule** checks each handler registered or scanned for a message of the kind. It gets a `HandlerInfo` — the message type, the handler and its return annotation — and returns why the handler can't be registered, or `None` if it can:

```python
from mediary import RuleViolation
from mediary.kinds import HandlerInfo


def returns_rows(info: HandlerInfo) -> str | None:
    if info.returns is type(None):
        return "a report must return its rows"
    return None


def named_after_the_report(info: HandlerInfo) -> str | None:
    expected = f"build_{info.message_type.__name__.lower()}"
    if getattr(info.handler, "__name__", "") != expected:
        return f"a report's handler is named {expected}"
    return None


audit_report = define_kind(
    "audit_report", dispatch="send", rules=[returns_rows, named_after_the_report]
)


@audit_report
class Logins(Returns[list[str]]):
    pass


async def build_logins(report: Logins) -> list[str]:
    return ["ada", "grace"]


async def logins(report: Logins) -> list[str]:
    return []


mediator = Mediator()
try:
    mediator.register(Logins, logins)
except RuleViolation as error:
    reason = str(error)
assert "named build_logins" in reason

mediator.register(Logins, build_logins)
assert await mediator.send(Logins()) == ["ada", "grace"]
```

A rule violation raises `RuleViolation` from `register`; `scan` collects them with every other problem into its `ScanError`, so broken handlers never reach production.

## A kind's own handler and behavior decorators

`handler_for(kind)` makes a `@handler` for the kind's messages only, and `behavior_for(kind)` a `@behavior` that wraps only them. They take the same arguments as `@handler` and `@behavior` (but no `kinds=`, which is fixed). A handler the first marks is rejected, with a `RuleViolation` naming the handler and the message, if it is registered or scanned for a message of another kind:

```python
from mediary import Next, request
from mediary.kinds import behavior_for, handler_for

job_handler = handler_for(job)
job_behavior = behavior_for(job)
started = []


@job_handler
async def compress_image(job: ResizeImage) -> str:
    return f"{job.path} compressed"


@job_behavior(order=-10)
async def log_jobs(job: object, next: Next[str]) -> str:
    started.append(type(job).__name__)
    return await next()


mediator = Mediator()
mediator.register(ResizeImage, compress_image)
mediator.use(log_jobs)
assert await mediator.send(ResizeImage("cat.png")) == "cat.png compressed"
assert started == ["ResizeImage"]


@request
class Ping(Returns[str]):
    pass


@job_handler
async def ping(request: Ping) -> str:
    return "pong"


try:
    mediator.register(Ping, ping)
except RuleViolation as error:
    reason = str(error)
assert "handles only @job messages" in reason
```

The [CQRS](cqrs.md) pack's `@command_handler` and `@command_behavior`, and their counterparts, are made this way.

## Inspecting kinds

`kind_of(cls)` returns the `Kind` a class is decorated as, or `None` if it isn't a message — useful in behaviors and tooling:

```python
from mediary.kinds import kind_of

assert kind_of(Logins).name == "audit_report"
assert kind_of(Logins).dispatch == "send"
assert kind_of(str) is None
```
