"""Package scanning: import every module under some roots and collect their `@handler`s."""

import importlib
import pkgutil
from collections.abc import Iterable, Iterator
from types import ModuleType

from ._handlers import is_handler


def discover(roots: Iterable[str | ModuleType]) -> tuple[list[object], list[Exception]]:
    """Import each root and all its submodules; return their handlers and any import errors.

    Handlers are the `@handler` classes and functions defined at module level.

    A handler is collected from the module that defines it, so re-exports don't repeat it.
    Modules are visited in a stable order: each root, then its submodules sorted by name.
    """
    problems: list[Exception] = []
    handlers: dict[object, None] = {}
    seen: set[str] = set()
    for root in roots:
        name = root if isinstance(root, str) else root.__name__
        for module in _walk(name, seen, problems):
            for value in vars(module).values():
                if is_handler(value) and getattr(value, "__module__", None) == module.__name__:
                    handlers[value] = None
    return list(handlers), problems


def _walk(name: str, seen: set[str], problems: list[Exception]) -> Iterator[ModuleType]:
    if name in seen:
        return
    seen.add(name)
    try:
        module = importlib.import_module(name)
    except Exception as exc:
        exc.add_note(f"raised while mediary was importing {name!r} during scan")
        problems.append(exc)
        return
    yield module
    path = getattr(module, "__path__", None)
    if path is not None:
        for info in pkgutil.iter_modules(path, prefix=f"{name}."):
            yield from _walk(info.name, seen, problems)
