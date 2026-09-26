"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidHandlerSignature,
    MediaryError,
    NotARequest,
    ScanError,
)
from ._handlers import Handler, handler
from ._markers import Returns, request
from ._mediator import Mediator

__version__: str = version("mediary")

__all__ = [
    "DuplicateHandler",
    "Handler",
    "HandlerNotFound",
    "InvalidHandlerSignature",
    "MediaryError",
    "Mediator",
    "NotARequest",
    "Returns",
    "ScanError",
    "__version__",
    "handler",
    "request",
]
