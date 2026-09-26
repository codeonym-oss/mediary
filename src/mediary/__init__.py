"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._behaviors import Behavior, Next, behavior
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidBehaviorSignature,
    InvalidHandlerSignature,
    MediaryError,
    NotANotification,
    NotARequest,
    ScanError,
)
from ._handlers import Handler, handler
from ._markers import Returns, notification, request
from ._mediator import Mediator
from ._publishing import Concurrent, PublishStrategy, Sequential
from ._resolving import Resolver

__version__: str = version("mediary")

__all__ = [
    "Behavior",
    "Concurrent",
    "DuplicateHandler",
    "Handler",
    "HandlerNotFound",
    "InvalidBehaviorSignature",
    "InvalidHandlerSignature",
    "MediaryError",
    "Mediator",
    "Next",
    "NotANotification",
    "NotARequest",
    "PublishStrategy",
    "Resolver",
    "Returns",
    "ScanError",
    "Sequential",
    "__version__",
    "behavior",
    "handler",
    "notification",
    "request",
]
