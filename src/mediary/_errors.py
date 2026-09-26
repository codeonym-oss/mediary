"""The exceptions mediary raises. All of them derive from `MediaryError`."""

from collections.abc import Sequence


def _name(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


class MediaryError(Exception):
    """Base class for every error raised by mediary."""


class HandlerNotFound(MediaryError, LookupError):
    """No handler is registered for the type of the request that was sent."""

    def __init__(self, request_type: type) -> None:
        self.request_type = request_type
        super().__init__(
            f"No handler registered for {_name(request_type)}. Is the class decorated with "
            "@request, and is its handler registered with this mediator?"
        )


class DuplicateHandler(MediaryError, ValueError):
    """A second handler was registered for a request type that already has one."""

    def __init__(self, request_type: type, existing: type, duplicate: type) -> None:
        self.request_type = request_type
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(
            f"{_name(request_type)} already has a handler, {_name(existing)}; "
            f"cannot also register {_name(duplicate)}. A request has exactly one handler."
        )


class NotARequest(MediaryError, TypeError):
    """A handler was registered for a class that isn't decorated as a request."""

    def __init__(self, cls: type) -> None:
        self.cls = cls
        super().__init__(
            f"{_name(cls)} is not a request. Decorate it with @request "
            "(subclasses of a request must be decorated too)."
        )


class InvalidHandlerSignature(MediaryError, TypeError):
    """A handler doesn't have the shape mediary can call."""

    def __init__(self, handler: type, reason: str) -> None:
        self.handler = handler
        super().__init__(f"Invalid handler {_name(handler)}: {reason}")


class ScanError(MediaryError):
    """`Mediator.scan` found problems; `errors` holds every one of them.

    Nothing from the failed scan is registered.
    """

    def __init__(self, errors: Sequence[Exception]) -> None:
        self.errors = tuple(errors)
        lines = "".join(f"\n  - {type(error).__name__}: {error}" for error in self.errors)
        super().__init__(f"scan found {len(self.errors)} problem(s):{lines}")
