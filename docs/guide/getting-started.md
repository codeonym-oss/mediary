# Getting started

## Install

```sh
pip install mediary  # or: uv add mediary
```

mediary needs Python 3.11 or later and has no dependencies. It runs on asyncio: handlers are `async`, and so are `send` and `publish`.

## Requests and handlers

A **request** is a message that asks for something and gets one result back. Declare it as any class — a dataclass, a Pydantic model, an attrs class — decorated with `@request`, and say what its handler returns with `Returns[...]`:

```python title="shop/orders.py"
from dataclasses import dataclass

from mediary import Returns, handler, request


@request
@dataclass
class PlaceOrder(Returns[int]):
    item: str
    quantity: int


@handler
class PlaceOrderHandler:
    async def handle(self, request: PlaceOrder) -> int:
        return 42  # the new order's id
```

A **handler** is a class with an async `handle` method, or an async function. Nothing to inherit: `@handler` marks it for scanning, and the type hint of its request parameter says which request it serves. Each request has exactly one handler.

## Scan, then send

Make one `Mediator` at startup, and scan the packages that hold your handlers:

```python
from mediary import Mediator
from shop.orders import PlaceOrder

mediator = Mediator()
mediator.scan("shop")  # imports shop and its submodules, registers each @handler

order_id = await mediator.send(PlaceOrder("book", 2))
assert order_id == 42
```

`send` is typed from the request's `Returns[...]`: type checkers know `order_id` is an `int`. The code that sends `PlaceOrder` never imports its handler, so either can change without the other.

!!! note "Top-level `await`"
    The examples use top-level `await`, as in `python -m asyncio` or a notebook. In an app, they live inside `async def`s.

## Function handlers

A handler can be an async function too. Its first parameter is the request; the others are [dependencies](dependency-injection.md), resolved by type hint:

```python title="shop/users.py"
from dataclasses import dataclass

from mediary import Returns, handler, request


@request
@dataclass
class GetUserName(Returns[str]):
    user_id: int


@handler
async def get_user_name(request: GetUserName) -> str:
    return {1: "Ada"}.get(request.user_id, "nobody")
```

```python
from shop.users import GetUserName

mediator = Mediator()
mediator.scan("shop")
assert await mediator.send(GetUserName(1)) == "Ada"
```

To serve a request other than the one the parameter is hinted with — a base class, say — name it: `@handler(GetUserName)`.

## Scanning finds every mistake at once

Scanning is all or nothing. It reports every problem it finds — a handler without a request hint, two handlers for one request, a module that fails to import — together, in one `ScanError`, and registers nothing:

```python title="broken/handlers.py"
from mediary import Returns, handler, request


@request
class Ping(Returns[str]):
    pass


@handler
async def pong(request: Ping) -> str:
    return "pong"


@handler
async def also_pong(request: Ping) -> str:
    return "pong!"
```

```python
from mediary import ScanError

mediator = Mediator()
try:
    mediator.scan("broken")
except ScanError as error:
    problems = error.errors
assert [type(problem).__name__ for problem in problems] == ["DuplicateHandler"]
```

So wiring mistakes surface when the app starts, not at the first request that hits them.

## Registering by hand

`register` does what `scan` does, for one handler, and needs no decorator on it. It suits libraries, tests, and apps that prefer explicit wiring:

```python
from mediary import Returns, request


@request
class Echo(Returns[str]):
    def __init__(self, text: str) -> None:
        self.text = text


async def echo(request: Echo) -> str:
    return request.text


mediator = Mediator()
mediator.register(Echo, echo)
assert await mediator.send(Echo("hi")) == "hi"
```

The request type still needs its decorator: `@request` is what tells mediary it is sent to one handler (a `@notification` is published to many).

## Errors

Every error mediary raises is a `MediaryError`:

| Error | Raised when |
|---|---|
| `HandlerNotFound` | `send` or `stream` finds no handler for the request's exact type |
| `DuplicateHandler` | a request would get a second handler |
| `NotARequest`, `NotANotification` | a type isn't decorated as the right kind of message |
| `InvalidHandlerSignature`, `InvalidBehaviorSignature` | a handler or behavior has the wrong shape |
| `RuleViolation` | a handler breaks a rule of its message's kind (see [custom kinds](custom-kinds.md)) |
| `ScanError` | `scan` found problems; they are in `.errors` |
| `HandlerTimeout` | a `TimeoutBehavior` gave up on a handler |

Errors your handlers raise propagate to the caller unchanged.

Next: give handlers their [dependencies](dependency-injection.md).
