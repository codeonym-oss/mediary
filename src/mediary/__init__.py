"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._behaviors import Behavior, Next, NextStream, StreamBehavior, behavior
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
from ._handlers import Handler, StreamHandler, handler
from ._markers import Returns, Yields, notification, request, stream_request
from ._mediator import Mediator
from ._publishing import Concurrent, PublishStrategy, Sequential
from ._resolving import Resolver
from ._retryable import TransientError, retryable
from ._streaming import Stream

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
    "NextStream",
    "NotANotification",
    "NotARequest",
    "PublishStrategy",
    "Resolver",
    "Returns",
    "RuleViolation",
    "ScanError",
    "Sequential",
    "Stream",
    "StreamBehavior",
    "StreamHandler",
    "TransientError",
    "Yields",
    "__version__",
    "behavior",
    "handler",
    "notification",
    "request",
    "retryable",
    "stream_request",
]
