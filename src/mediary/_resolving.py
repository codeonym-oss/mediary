"""The ``Resolver`` seam, and reading the parameters of handler and behavior callables."""

import inspect
import typing
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

_T = TypeVar("_T")

ErrorFactory = Callable[[Any, str], Exception]
"""Builds the error to raise for a malformed callable: ``(source, reason) -> exception``."""


class Resolver(Protocol):
    """Supplies handler and behavior instances, and the dependencies of functions.

    Plug a DI container in by adapting it to ``resolve``, which may be sync or async. The
    default resolver calls ``cls()``.

    Example:
        .. code-block:: python

            class ContainerResolver:
                def __init__(self, container: Container) -> None:
                    self.container = container

                def resolve(self, cls: type[T]) -> T:
                    return self.container.get(cls)

            mediator = Mediator(resolver=ContainerResolver(container))

    """

    def resolve(self, cls: type[_T], /) -> _T | Awaitable[_T]:
        """Return an instance of ``cls``."""
        ...


class DefaultResolver:
    """Instantiates each type with no arguments."""

    def resolve(self, cls: type[_T], /) -> _T:
        """Return ``cls()``."""
        return cls()


async def resolve(resolver: Resolver, cls: Any) -> Any:
    """Resolve ``cls`` with ``resolver``, awaiting the result if it is awaitable."""
    instance = resolver.resolve(cls)
    return await instance if inspect.isawaitable(instance) else instance


def require_async(source: Any, fn: Any, needs: str, error: ErrorFactory) -> Callable[..., Any]:
    """Return ``fn`` if it is an async function or generator, else raise ``error(source, ...)``."""
    if not (inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn)):
        sync = "it is sync, but must be async: " if inspect.isfunction(fn) else ""
        raise error(source, f"{sync}it needs {needs}")
    return fn


@dataclass(frozen=True, slots=True)
class Shape:
    """The parameters of a handler or behavior callable.

    ``leading`` are the parameters mediary passes positionally (the request, then ``next`` for
    behaviors); ``hints`` their resolved type hints. The rest are dependencies, resolved by
    type hint on each call.
    """

    leading: tuple[inspect.Parameter, ...]
    hints: dict[str, Any]
    positional: tuple[Any, ...] = ()
    keyword: tuple[tuple[str, Any], ...] = ()

    def hint(self, index: int) -> Any:
        """Return the type hint of the ``index``-th leading parameter, or None."""
        return self.hints.get(self.leading[index].name)

    async def dependencies(self, resolver: Resolver) -> tuple[list[Any], dict[str, Any]]:
        """Resolve the dependencies into positional and keyword arguments."""
        args = [await resolve(resolver, hint) for hint in self.positional]
        kwargs = {name: await resolve(resolver, hint) for name, hint in self.keyword}
        return args, kwargs


_POSITIONAL = (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
_VARIADIC = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)


def shape(
    source: Any,
    fn: Callable[..., Any],
    *,
    leading: tuple[str, ...],
    method: bool,
    error: ErrorFactory,
) -> Shape:
    """Read the shape of ``fn``, which takes ``leading`` positional parameters then dependencies.

    For a ``method``, ``self`` is skipped and any further parameters are left alone (a class gets
    its dependencies through the resolver instead).

    Raises:
        Exception: from ``error(source, reason)``, when a leading parameter is missing or not
            positional, a dependency is variadic or unhinted, or the hints can't be resolved.

    """
    params = list(inspect.signature(fn).parameters.values())[1 if method else 0 :]
    if len(params) < len(leading) or any(p.kind not in _POSITIONAL for p in params[: len(leading)]):
        wanted = ", ".join(leading)
        raise error(source, f"it must take positional parameters ({wanted})")
    try:
        hints = typing.get_type_hints(fn)
    except Exception as exc:
        raise error(source, f"cannot resolve its type hints ({type(exc).__name__}: {exc})") from exc
    result = Shape(tuple(params[: len(leading)]), hints)
    if method:
        return result
    positional: list[Any] = []
    keyword: list[tuple[str, Any]] = []
    for param in params[len(leading) :]:
        if param.kind in _VARIADIC:
            raise error(source, f"dependencies are resolved one by one, so `{param}` isn't allowed")
        if param.name not in hints:
            raise error(
                source, f"the dependency `{param.name}` needs a type hint so it can be resolved"
            )
        if param.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(hints[param.name])
        else:
            keyword.append((param.name, hints[param.name]))
    return Shape(result.leading, hints, tuple(positional), tuple(keyword))
