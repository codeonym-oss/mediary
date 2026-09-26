# AnyIO and trio

mediary runs on asyncio with the standard library alone. To run it on [trio](https://trio.readthedocs.io/) — or any event loop [AnyIO](https://anyio.readthedocs.io/) supports — install the extra:

```sh
pip install mediary[anyio]
```

There is nothing to configure. `send`, `publish` and `stream` don't depend on an event loop; the three built-ins that do — the `Concurrent` publish strategy, `RetryBehavior`'s sleep between attempts and `TimeoutBehavior` — use asyncio when it is running, and AnyIO otherwise. Asyncio apps never import AnyIO, whether it is installed or not.

<!-- requires: trio,anyio -->
```python
import trio

from mediary import Concurrent, HandlerTimeout, Mediator, notification, request
from mediary.behaviors import TimeoutBehavior


@notification
class Started:
    pass


@request
class Slow:
    pass


greeted = []


async def greet(event: Started) -> None:
    greeted.append("hello")


async def slow(request: Slow) -> None:
    await trio.sleep(10)


async def main() -> None:
    mediator = Mediator(publish_strategy=Concurrent())  # a trio nursery here
    mediator.register(Started, greet)
    mediator.register(Slow, slow)
    mediator.use(TimeoutBehavior(seconds=0.01))  # a trio cancel scope here

    await mediator.publish(Started())
    try:
        await mediator.send(Slow())
    except HandlerTimeout as error:
        print(error)  # Slow was not handled within 0.01s


trio.run(main)
assert greeted == ["hello"]
```

Without the extra, the first of those built-ins used outside asyncio raises a `ModuleNotFoundError` that says to install it.

## Things to know under trio

- **Close streams with `async with`.** Trio can't finalize an async generator that is garbage-collected mid-iteration, and warns when one is. Iterate [streams](../guide/streams.md) inside `async with`, or call `aclose()`.
- **Your own code picks its primitives.** Handlers, behaviors and [publish strategies](../guide/notifications.md#your-own-strategy) you write use whatever your app uses: trio's, AnyIO's, or asyncio's.
- **Integrations follow their frameworks.** FastAPI runs on AnyIO already; check that the others you use support trio.

## Testing on both

mediary's own test suite runs every async test under asyncio and trio, with [AnyIO's pytest plugin](https://anyio.readthedocs.io/en/stable/testing.html). The `mediator` fixture works under either, and so does `RecordingMediator`.
