"""The built-ins that sleep, time out or run tasks, on each event loop: asyncio, and trio."""

import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from mediary import HandlerTimeout, Mediator, Returns, TransientError, request
from mediary._concurrency import _on_asyncio  # pyright: ignore[reportPrivateUsage]
from mediary.behaviors import RetryBehavior, TimeoutBehavior


@request
class Flaky(Returns[str]):
    pass


def flaky_mediator(behavior: Any) -> Mediator:
    calls: list[int] = []

    async def flaky(request: Flaky) -> str:
        calls.append(1)
        if len(calls) < 3:
            raise TransientError
        return "done"

    m = Mediator()
    m.register(Flaky, flaky)
    m.use(behavior)
    return m


async def test_retries_sleep_on_the_running_event_loop() -> None:
    m = flaky_mediator(RetryBehavior(base_delay=0.001, jitter=False))
    assert await m.send(Flaky()) == "done"


async def test_other_event_loops_need_anyio(
    anyio_backend_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if anyio_backend_name == "asyncio":
        pytest.skip("asyncio needs nothing but the standard library")
    monkeypatch.setitem(sys.modules, "anyio", None)  # as if it weren't installed
    m = flaky_mediator(TimeoutBehavior(seconds=1))
    with pytest.raises(ModuleNotFoundError, match=r"pip install mediary\[anyio\]") as exc:
        await m.send(Flaky())
    assert exc.value.name == "anyio"


def test_asyncio_needs_nothing_but_the_standard_library() -> None:
    script = textwrap.dedent(
        """
        import asyncio, sys
        sys.modules["anyio"] = None  # importing it fails
        from mediary import Concurrent, HandlerTimeout, Mediator, notification, request
        from mediary.behaviors import RetryBehavior, TimeoutBehavior

        @request
        class Slow: pass

        @notification
        class Happened: pass

        async def slow(request: Slow) -> None:
            await asyncio.sleep(1)

        async def happened(event: Happened) -> None:
            pass

        async def main() -> None:
            m = Mediator(publish_strategy=Concurrent())
            m.register(Slow, slow)
            m.register(Happened, happened)
            await m.publish(Happened())
            m.use(TimeoutBehavior(seconds=0.01))
            m.use(RetryBehavior(retry_on=(HandlerTimeout,), base_delay=0.001), order=-1)
            try:
                await m.send(Slow())
            except HandlerTimeout:
                print("ok")

        asyncio.run(main())
        """
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, check=True)
    assert result.stdout.decode().strip() == "ok"


async def test_the_running_event_loop_is_detected(
    anyio_backend_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _on_asyncio() is (anyio_backend_name == "asyncio")
    if anyio_backend_name == "asyncio":
        monkeypatch.delitem(sys.modules, "sniffio")  # as in an app that never loaded it
        assert _on_asyncio()


def test_no_event_loop_is_not_asyncio(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not _on_asyncio()
    monkeypatch.delitem(sys.modules, "sniffio")
    assert not _on_asyncio()


def test_trio_is_detected_even_inside_asyncio() -> None:
    import asyncio

    import trio

    @request
    class Slow:
        pass

    async def slow(request: Slow) -> None:
        await trio.sleep(1)

    m = Mediator()
    m.register(Slow, slow)
    m.use(TimeoutBehavior(seconds=0.01))

    async def on_trio() -> None:
        with pytest.raises(HandlerTimeout):
            await m.send(Slow())

    async def on_asyncio() -> None:
        trio.run(on_trio)  # asyncio's running loop is still set on this thread

    # Off the main thread, where neither loop installs signal handling: on Windows, theirs
    # collide.
    with ThreadPoolExecutor(1) as thread:
        thread.submit(asyncio.run, on_asyncio()).result()
