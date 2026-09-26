"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._behaviors import Behavior, Next, behavior
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    HandlerTimeout,
    InvalidBehaviorSignature,
    InvalidHandlerSignature,
    MediaryError,
    NotANotification,
    NotARequest,
    RuleViolation,
    ScanError,
)
from ._handlers import Handler, handler
from ._markers import Returns, notification, request
from ._mediator import Mediator
from ._publishing import Concurrent, PublishStrategy, Sequential
from ._resolving import Resolver
from ._retryable import TransientError, retryable

__version__: str = version("mediary")

__all__ = [
    "Behavior",
    "Concurrent",
    "DuplicateHandler",
    "Handler",
    "HandlerNotFound",
    "HandlerTimeout",
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
    "RuleViolation",
    "ScanError",
    "Sequential",
    "TransientError",
    "__version__",
    "behavior",
    "handler",
    "notification",
    "request",
    "retryable",
]
