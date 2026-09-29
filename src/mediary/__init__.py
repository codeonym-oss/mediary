"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version
from typing import TYPE_CHECKING

from ._behaviors import Behavior, Next, NextStream, StreamBehavior, behavior
from ._deprecation import alias
from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    HandlerTimeout,
    InvalidBehavior,
    InvalidHandler,
    MediaryError,
    NotAMessage,
    NotANotification,
    RuleViolation,
    ScanError,
)
from ._handlers import Handler, StreamHandler, SyncHandler, handler
from ._markers import Returns, Yields, notification, request, stream_request
from ._mediator import Mediator
from ._publishing import Concurrent, NotificationCall, PublishStrategy, Sequential
from ._resolving import Resolver
from ._retryable import TransientError, retryable
from ._senders import Publisher, Sender
from ._streaming import Stream

__version__: str = version("mediary")

_DEPRECATED = {
    "NotARequest": ("NotAMessage", NotAMessage),
    "InvalidHandlerSignature": ("InvalidHandler", InvalidHandler),
    "InvalidBehaviorSignature": ("InvalidBehavior", InvalidBehavior),
}

if TYPE_CHECKING:
    from typing_extensions import deprecated

    @deprecated("NotARequest is deprecated; use NotAMessage")
    class NotARequest(NotAMessage): ...

    @deprecated("InvalidHandlerSignature is deprecated; use InvalidHandler")
    class InvalidHandlerSignature(InvalidHandler): ...

    @deprecated("InvalidBehaviorSignature is deprecated; use InvalidBehavior")
    class InvalidBehaviorSignature(InvalidBehavior): ...

else:

    def __getattr__(name: str) -> object:
        """Return a deprecated name's replacement, with a warning."""
        return alias(__name__, _DEPRECATED, name)


__all__ = [
    "Behavior",
    "Concurrent",
    "DuplicateHandler",
    "Handler",
    "HandlerNotFound",
    "HandlerTimeout",
    "InvalidBehavior",
    "InvalidHandler",
    "MediaryError",
    "Mediator",
    "Next",
    "NextStream",
    "NotAMessage",
    "NotANotification",
    "NotificationCall",
    "PublishStrategy",
    "Publisher",
    "Resolver",
    "Returns",
    "RuleViolation",
    "ScanError",
    "Sender",
    "Sequential",
    "Stream",
    "StreamBehavior",
    "StreamHandler",
    "SyncHandler",
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
