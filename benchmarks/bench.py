"""Measure mediary's overhead, each case against its baseline where it has one.

Run ``uv run python benchmarks/bench.py`` for the full suite, or add ``--quick`` for a smoke run
that only checks every case still works (CI runs it on each pull request). Each timing is the
best of several repeats, per operation, on asyncio.
"""

import argparse
import asyncio
import importlib
import platform
import sys
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mediary
from mediary import (
    Concurrent,
    Mediator,
    Next,
    Returns,
    Sequential,
    Yields,
    notification,
    request,
    stream_request,
)

STREAM_ITEMS = 1000


@dataclass(frozen=True)
class Settings:
    """How long to measure: ``number`` operations per timing, the best of ``repeat`` timings."""

    number: int
    repeat: int
    scanned_handlers: int
    scan_repeat: int


FULL = Settings(number=20_000, repeat=7, scanned_handlers=300, scan_repeat=5)
QUICK = Settings(number=50, repeat=2, scanned_handlers=20, scan_repeat=1)


@dataclass(frozen=True)
class Result:
    """One case's time per operation in seconds, and its baseline's if it has one."""

    case: str
    seconds: float
    baseline: str = ""
    baseline_seconds: float | None = None


@request
@dataclass(frozen=True, slots=True)
class Ping(Returns[int]):
    """The request every ``send`` case sends."""


@notification
@dataclass(frozen=True, slots=True)
class Tick:
    """The notification every ``publish`` case publishes."""


@stream_request
@dataclass(frozen=True, slots=True)
class Count(Yields[int]):
    """The stream request of the stream case."""

    items: int


async def ping(request: Ping) -> int:
    """Handle ``Ping``, doing nothing, so only the dispatch is measured."""
    return 1


async def count(request: Count) -> AsyncIterator[int]:
    """Yield ``request.items`` numbers."""
    for n in range(request.items):
        yield n


def passthrough() -> Callable[[object, Next[Any]], Awaitable[Any]]:
    """Return a new behavior that only calls ``next``: each one is a distinct behavior."""

    async def behavior(message: object, next: Next[Any]) -> Any:
        return await next()

    return behavior


Subscriber = Callable[[Tick], Coroutine[Any, Any, None]]


def subscriber() -> Subscriber:
    """Return a new notification handler that does nothing."""

    async def handle(event: Tick) -> None:
        return None

    return handle


async def per_operation(run: Callable[[], Awaitable[object]], settings: Settings) -> float:
    """Return the best, over ``settings.repeat`` timings, of the seconds ``run()`` takes."""
    await run()  # warm up
    best = float("inf")
    for _ in range(settings.repeat):
        started = time.perf_counter()
        for _ in range(settings.number):
            await run()
        best = min(best, (time.perf_counter() - started) / settings.number)
    return best


async def bench_send(settings: Settings) -> list[Result]:
    """Time ``send`` with 0, 1, 5 and 10 behaviors, against calling the handler directly."""
    message = Ping()
    direct = await per_operation(lambda: ping(message), settings)
    results: list[Result] = []
    for behaviors in (0, 1, 5, 10):
        m = Mediator()
        m.register(Ping, ping)
        for _ in range(behaviors):
            m.use(passthrough())
        seconds = await per_operation(lambda m=m: m.send(message), settings)
        results.append(
            Result(
                f"send, {plural(behaviors, 'behavior')}", seconds, "handler called directly", direct
            )
        )
    return results


async def bench_publish(settings: Settings) -> list[Result]:
    """Time ``publish`` to 1, 5 and 20 handlers (and to 20, 5 at a time) against direct calls."""
    event = Tick()
    results: list[Result] = []
    for handlers in (1, 5, 20):
        functions = [subscriber() for _ in range(handlers)]
        sequential = Mediator(publish_strategy=Sequential())
        concurrent = Mediator(publish_strategy=Concurrent())
        for handle in functions:
            sequential.register(Tick, handle)
            concurrent.register(Tick, handle)

        async def in_turn(functions: list[Subscriber] = functions) -> None:
            for handle in functions:
                await handle(event)

        async def in_tasks(functions: list[Subscriber] = functions) -> None:
            async with asyncio.TaskGroup() as group:
                for handle in functions:
                    group.create_task(handle(event))

        results += [
            Result(
                f"publish, {plural(handlers, 'handler')}, sequential",
                await per_operation(lambda m=sequential: m.publish(event), settings),
                "awaited in turn",
                await per_operation(in_turn, settings),
            ),
            Result(
                f"publish, {plural(handlers, 'handler')}, concurrent",
                await per_operation(lambda m=concurrent: m.publish(event), settings),
                "tasks in a TaskGroup",
                await per_operation(in_tasks, settings),
            ),
        ]
    functions = [subscriber() for _ in range(20)]
    limited = Mediator(publish_strategy=Concurrent(limit=5))
    for handle in functions:
        limited.register(Tick, handle)

    async def all_in_tasks() -> None:
        async with asyncio.TaskGroup() as group:
            for handle in functions:
                group.create_task(handle(event))

    results.append(
        Result(
            "publish, 20 handlers, concurrent, limit 5",
            await per_operation(lambda: limited.publish(event), settings),
            "tasks in a TaskGroup",
            await per_operation(all_in_tasks, settings),
        )
    )
    return results


async def bench_stream(settings: Settings) -> list[Result]:
    """Time streaming ``STREAM_ITEMS`` items, against iterating the generator directly."""
    m = Mediator()
    m.register(Count, count)
    message = Count(STREAM_ITEMS)
    few = Settings(max(1, settings.number // 100), settings.repeat, 0, 0)

    async def directly() -> None:
        async for _ in count(message):
            pass

    async def streamed() -> None:
        async with m.stream(message) as items:
            async for _ in items:
                pass

    return [
        Result(
            f"stream of {STREAM_ITEMS} items",
            await per_operation(streamed, few),
            "generator iterated directly",
            await per_operation(directly, few),
        )
    ]


def write_package(root: Path, handlers: int) -> str:
    """Write a package of ``handlers`` requests and handlers, ten per module; return its name."""
    name = f"bench_{uuid.uuid4().hex}"
    package = root / name
    package.mkdir()
    (package / "__init__.py").touch()
    for module in range(0, handlers, 10):
        lines = ["from mediary import Returns, handler, request", ""]
        for n in range(module, min(module + 10, handlers)):
            lines += [
                "@request",
                f"class Request{n}(Returns[int]):",
                "    pass",
                "",
                "@handler",
                f"async def handle{n}(request: Request{n}) -> int:",
                f"    return {n}",
                "",
            ]
        (package / f"module{module // 10}.py").write_text("\n".join(lines))
    importlib.invalidate_caches()
    return name


def import_all(name: str) -> None:
    """Import package ``name`` and its modules, as ``scan`` does, without registering anything."""
    package = importlib.import_module(name)
    for path in sorted(Path(package.__path__[0]).glob("module*.py")):
        importlib.import_module(f"{name}.{path.stem}")


def bench_scan(settings: Settings) -> list[Result]:
    """Time ``scan`` of a new package, against importing its modules, and of an imported one."""
    first, again, imports = float("inf"), float("inf"), float("inf")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        sys.path.insert(0, directory)
        try:
            for _ in range(settings.scan_repeat):
                plain = write_package(root, settings.scanned_handlers)
                started = time.perf_counter()
                import_all(plain)
                imports = min(imports, time.perf_counter() - started)

                scanned = write_package(root, settings.scanned_handlers)
                started = time.perf_counter()
                Mediator().scan(scanned)
                first = min(first, time.perf_counter() - started)

                started = time.perf_counter()
                Mediator().scan(scanned)
                again = min(again, time.perf_counter() - started)
        finally:
            sys.path.remove(directory)
    handlers = settings.scanned_handlers
    return [
        Result(f"scan of {handlers} handlers, first", first, "importing its modules", imports),
        Result(f"scan of {handlers} handlers, already imported", again),
    ]


def plural(n: int, noun: str) -> str:
    """Return ``n`` and ``noun``, in the plural unless ``n`` is 1."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def duration(seconds: float) -> str:
    """Format ``seconds`` in the unit that suits it."""
    for unit, scale in (("s", 1.0), ("ms", 1e-3), ("µs", 1e-6)):
        if seconds >= scale:
            return f"{seconds / scale:.2f} {unit}"
    return f"{seconds / 1e-9:.0f} ns"


def table(results: list[Result]) -> str:
    """Return ``results`` as a Markdown table."""
    rows = [
        "| Case | mediary | Baseline | Baseline time | Overhead |",
        "|---|--:|---|--:|--:|",
    ]
    for r in results:
        if r.baseline_seconds is None:
            rows.append(f"| {r.case} | {duration(r.seconds)} | | | |")
            continue
        overhead = f"+{duration(max(r.seconds - r.baseline_seconds, 0.0))}"
        rows.append(
            f"| {r.case} | {duration(r.seconds)} | {r.baseline} | "
            f"{duration(r.baseline_seconds)} | {overhead} |"
        )
    return "\n".join(rows)


def environment() -> str:
    """Describe the machine and versions the results were measured on."""
    cpu = platform.processor() or platform.machine()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        models = [ln for ln in cpuinfo.read_text().splitlines() if ln.startswith("model name")]
        if models:
            cpu = models[0].split(":", 1)[1].strip()
    return (
        f"mediary {mediary.__version__}, {platform.python_implementation()} "
        f"{platform.python_version()}, {platform.system()} {platform.release()}, {cpu}"
    )


async def run_async(settings: Settings) -> list[Result]:
    """Run the cases that need an event loop."""
    return [
        *await bench_send(settings),
        *await bench_publish(settings),
        *await bench_stream(settings),
    ]


def main() -> None:
    """Run the suite and print the results table."""
    parser = argparse.ArgumentParser(description="Measure mediary's overhead.")
    parser.add_argument("--quick", action="store_true", help="run each case briefly, as a check")
    settings = QUICK if parser.parse_args().quick else FULL
    results = [*asyncio.run(run_async(settings)), *bench_scan(settings)]
    print(environment())
    print()
    print(table(results))


if __name__ == "__main__":
    main()
