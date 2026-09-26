"""Package scanning: import every module under some roots and collect what is decorated."""

import importlib
import pkgutil
from collections.abc import Container, Iterable, Iterator
from types import ModuleType

from ._markers import marker_of


def discover(
    roots: Iterable[str | ModuleType], kinds: Container[str]
) -> tuple[list[object], list[Exception]]:
    """Import each root and all its submodules; return what they define, and any import errors.

    What is collected: the module-level classes and functions whose marker kind is in ``kinds``.
    Each is collected from the module that defines it, so re-exports don't repeat it.
    Modules are visited in a stable order: each root, then its submodules sorted by name.
    """
    problems: list[Exception] = []
    found: dict[object, None] = {}
    seen: set[str] = set()
    for root in roots:
        name = root if isinstance(root, str) else root.__name__
        for module in _walk(name, seen, problems):
            for value in vars(module).values():
                marker = marker_of(value)
                if (
                    marker is not None
                    and marker.kind in kinds
                    and getattr(value, "__module__", None) == module.__name__
                ):
                    found[value] = None
    return list(found), problems


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
