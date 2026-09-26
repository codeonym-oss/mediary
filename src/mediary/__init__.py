"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._behaviors import Behavior, Next, behavior
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidBehaviorSignature,
    InvalidHandlerSignature,
    MediaryError,
    NotARequest,
    ScanError,
)
from ._handlers import Handler, handler
from ._markers import Returns, request
from ._mediator import Mediator
from ._resolving import Resolver

__version__: str = version("mediary")

__all__ = [
    "Behavior",
    "DuplicateHandler",
    "Handler",
    "HandlerNotFound",
    "InvalidBehaviorSignature",
    "InvalidHandlerSignature",
    "MediaryError",
    "Mediator",
    "Next",
    "NotARequest",
    "Resolver",
    "Returns",
    "ScanError",
    "__version__",
    "behavior",
    "handler",
    "request",
]
