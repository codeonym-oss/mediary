"""Typed, decorator-driven mediator + CQRS for Python."""

from importlib.metadata import version

from ._errors import (
    DuplicateHandler,
    HandlerNotFound,
    InvalidHandlerSignature,
    MediaryError,
    NotARequest,
)
from ._markers import Returns, request
from ._mediator import Handler, Mediator

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
    "__version__",
    "request",
]
