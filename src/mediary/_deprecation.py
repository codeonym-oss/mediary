"""Deprecated names: they keep working until 1.0, with a warning that names the replacement."""

import functools
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])


def warn(old: str, new: str) -> None:
    """Warn, at the caller of the deprecated API, that ``old`` is replaced by ``new``."""
    warnings.warn(
        f"{old} is deprecated and will be removed in 1.0; use {new}",
        DeprecationWarning,
        stacklevel=3,
    )


def alias(module: str, aliases: dict[str, tuple[str, object]], name: str) -> object:
    """Return the replacement for the deprecated ``name`` of ``module``, with a warning.

    ``aliases`` maps each deprecated name to its replacement's name and value. It backs a
    module's ``__getattr__``, so a deprecated name warns wherever it is looked up.

    Raises:
        AttributeError: ``name`` isn't a deprecated name of ``module``.

    """
    if name not in aliases:
        raise AttributeError(f"module {module!r} has no attribute {name!r}")
    new, value = aliases[name]
    warn(f"{module}.{name}", f"{module}.{new}")
    return value


def attribute(old: str, new: str) -> property:
    """Return a property that reads the attribute ``new`` under the deprecated name ``old``."""

    def get(self: object) -> Any:
        warn(f"{type(self).__name__}.{old}", f".{new}")
        return getattr(self, new)

    return property(get, doc=f"Deprecated: use ``{new}``.")


def positional_only(*names: str) -> Callable[[_F], _F]:
    """Accept the parameters ``names``, which follow ``self``, by keyword too, with a warning.

    ``names`` are the old names of parameters that are now positional-only.
    """

    def decorate(method: _F) -> _F:
        @functools.wraps(method)
        def wrapper(self: object, /, *args: Any, **kwargs: Any) -> Any:
            moved: list[str] = []
            for name in names[len(args) :]:
                if name not in kwargs:
                    break
                moved.append(name)
                args = (*args, kwargs.pop(name))
            if moved:
                warn(
                    f"passing {', '.join(moved)} to {method.__qualname__} by keyword",
                    "positional arguments",
                )
            return method(self, *args, **kwargs)

        return wrapper  # pyright: ignore[reportReturnType]

    return decorate
