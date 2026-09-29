import importlib
import sys
from typing import Any

import pytest
from conftest import MakePackage

from mediary import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidHandler,
    Mediator,
    NotAMessage,
    ScanError,
    handler,
    request,
)

REQUESTS = """
    from mediary import Returns, request

    @request
    class GetGreeting(Returns[str]):
        def __init__(self, name: str) -> None:
            self.name = name

    @request
    class Ping:
        pass
"""


def module(name: str) -> Any:
    return importlib.import_module(name)


async def test_scan_registers_handlers_throughout_the_package(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "requests.py": REQUESTS,
            "features/greetings/handlers.py": """
                from mediary import handler
                from ...requests import GetGreeting

                @handler
                class GetGreetingHandler:
                    async def handle(self, request: GetGreeting) -> str:
                        return f"hello {request.name}"
            """,
            "features/ping.py": """
                from mediary import handler
                from ..requests import Ping

                @handler
                class PingHandler:
                    async def handle(self, request: Ping) -> str:
                        return "pong"
            """,
        }
    )
    m = Mediator()
    m.scan(pkg)
    requests = module(f"{pkg}.requests")
    assert await m.send(requests.GetGreeting("ada")) == "hello ada"
    assert await m.send(requests.Ping()) == "pong"


async def test_handler_can_name_its_request_explicitly(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "requests.py": REQUESTS,
            "handlers.py": """
                from mediary import handler
                from .requests import Ping

                @handler(Ping)
                class PingHandler:
                    async def handle(self, request):
                        return "pong"
            """,
        }
    )
    m = Mediator()
    m.scan(pkg)
    assert await m.send(module(f"{pkg}.requests").Ping()) == "pong"


async def test_forward_references_resolve(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "postponed.py": """
                from __future__ import annotations
                from mediary import handler, request

                @handler
                class LaterHandler:
                    async def handle(self, request: Later) -> str:
                        return "postponed"

                @request
                class Later:
                    pass
            """,
            "quoted.py": """
                from mediary import handler, request

                @handler
                class QuotedHandler:
                    async def handle(self, request: "Quoted") -> str:
                        return "quoted"

                @request
                class Quoted:
                    pass
            """,
        }
    )
    m = Mediator()
    m.scan(pkg)
    assert await m.send(module(f"{pkg}.postponed").Later()) == "postponed"
    assert await m.send(module(f"{pkg}.quoted").Quoted()) == "quoted"


@pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 649 deferred annotations are 3.14+")
async def test_deferred_annotations_resolve(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "deferred.py": """
                from mediary import handler, request

                @handler
                class LaterHandler:
                    async def handle(self, request: Later) -> str:
                        return "deferred"

                @request
                class Later:
                    pass
            """
        }
    )
    m = Mediator()
    m.scan(pkg)
    assert await m.send(module(f"{pkg}.deferred").Later()) == "deferred"


async def test_scan_reports_every_problem_at_once_and_registers_nothing(
    make_package: MakePackage,
) -> None:
    pkg = make_package(
        {
            "requests.py": REQUESTS,
            "good.py": """
                from mediary import handler
                from .requests import GetGreeting

                @handler
                class GreetingHandler:
                    async def handle(self, request: GetGreeting) -> str:
                        return "hi"
            """,
            "problems.py": """
                from mediary import handler
                from .requests import GetGreeting, Ping

                class NotAMessage:
                    pass

                @handler
                class SecondGreetingHandler:
                    async def handle(self, request: GetGreeting) -> str:
                        return "hi again"

                @handler
                class UnmarkedTargetHandler:
                    async def handle(self, request: NotAMessage) -> None: ...

                @handler
                class UnresolvedHandler:
                    async def handle(self, request: "Missing") -> None: ...

                @handler
                class UnhintedHandler:
                    async def handle(self, request): ...

                @handler
                class UnionHandler:
                    async def handle(self, request: GetGreeting | Ping) -> None: ...

                @handler
                class NoRequestHandler:
                    async def handle(self) -> None: ...

                @handler
                class SyncGeneratorHandler:
                    def handle(self, request: Ping):
                        yield
            """,
            "broken.py": "raise RuntimeError('boom')",
        }
    )
    m = Mediator()
    with pytest.raises(ScanError, match=r"8 problem\(s\)") as exc:
        m.scan(pkg)

    errors = exc.value.errors
    kinds = [type(error) for error in errors]
    assert kinds.count(RuntimeError) == 1
    assert kinds.count(DuplicateHandler) == 1
    assert kinds.count(NotAMessage) == 1
    assert kinds.count(InvalidHandler) == 5
    messages = "\n".join(str(error) for error in errors)
    assert "cannot resolve its type hints" in messages
    assert "has no type hint" in messages
    assert "must be hinted with one class" in messages
    assert "must take positional parameters (request)" in messages
    assert "it is a sync generator" in messages
    runtime_error = next(error for error in errors if isinstance(error, RuntimeError))
    assert f"{pkg}.broken" in "".join(runtime_error.__notes__)

    # The valid handler in the same scan isn't registered either.
    with pytest.raises(HandlerNotFound):
        await m.send(module(f"{pkg}.requests").GetGreeting("ada"))


PING_HANDLER = """
    from mediary import handler
    from .requests import Ping

    @handler
    class PingHandler:
        async def handle(self, request: Ping) -> str:
            return "pong from " + __name__
"""


async def test_mediators_only_see_what_they_scanned(make_package: MakePackage) -> None:
    first = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    second = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    a, b = Mediator(), Mediator()
    a.scan(first)
    b.scan(second)
    assert await a.send(module(f"{first}.requests").Ping()) == f"pong from {first}.handlers"
    with pytest.raises(HandlerNotFound):
        await a.send(module(f"{second}.requests").Ping())
    with pytest.raises(HandlerNotFound):
        await b.send(module(f"{first}.requests").Ping())


async def test_scan_takes_several_roots_and_modules(make_package: MakePackage) -> None:
    first = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    second = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    m = Mediator()
    m.scan(first, f"{first}.handlers", module(f"{second}.handlers"))
    assert await m.send(module(f"{first}.requests").Ping()) == f"pong from {first}.handlers"
    assert await m.send(module(f"{second}.requests").Ping()) == f"pong from {second}.handlers"


async def test_scan_ignores_reexports_and_undecorated_classes(make_package: MakePackage) -> None:
    pkg = make_package(
        {
            "requests.py": REQUESTS,
            "handlers.py": PING_HANDLER,
            "reexport.py": "from .handlers import PingHandler",
            "plain.py": """
                from .requests import Ping

                class NotScanned:
                    async def handle(self, request: Ping) -> str:
                        return "ignored"
            """,
        }
    )
    m = Mediator()
    m.scan(pkg)
    assert await m.send(module(f"{pkg}.requests").Ping()) == f"pong from {pkg}.handlers"


async def test_scanning_again_registers_nothing_new(make_package: MakePackage) -> None:
    pkg = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    m = Mediator()
    m.scan(pkg)
    m.scan(pkg)
    assert await m.send(module(f"{pkg}.requests").Ping()) == f"pong from {pkg}.handlers"


async def test_manual_registration_works_alongside_scanning(make_package: MakePackage) -> None:
    pkg = make_package({"requests.py": REQUESTS, "handlers.py": PING_HANDLER})
    requests = module(f"{pkg}.requests")

    class ManualGreeting:
        async def handle(self, request: Any) -> str:
            return "manual"

    class ManualPing:
        async def handle(self, request: Any) -> str:
            return "manual"

    m = Mediator()
    m.register(requests.GetGreeting, ManualGreeting)
    m.scan(pkg)
    assert await m.send(requests.GetGreeting("ada")) == "manual"
    assert await m.send(requests.Ping()) == f"pong from {pkg}.handlers"

    other = Mediator()
    other.register(requests.Ping, ManualPing)
    with pytest.raises(ScanError) as exc:
        other.scan(pkg)
    assert [type(error) for error in exc.value.errors] == [DuplicateHandler]


def test_a_missing_package_is_reported() -> None:
    with pytest.raises(ScanError) as exc:
        Mediator().scan("no_such_package_for_mediary")
    assert isinstance(exc.value.errors[0], ModuleNotFoundError)


def test_handler_decorator_returns_the_class() -> None:
    @request
    class Ping:
        pass

    class Bare:
        async def handle(self, request: Ping) -> None: ...

    class Explicit:
        async def handle(self, request: Ping) -> None: ...

    assert handler(Bare) is Bare
    assert handler(Ping)(Explicit) is Explicit
