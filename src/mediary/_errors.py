"""The exceptions mediary raises. All of them derive from `MediaryError`."""

from collections.abc import Sequence


def _name(obj: object) -> str:
    return f"{getattr(obj, '__module__', '?')}.{getattr(obj, '__qualname__', obj)}"


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

    def __init__(self, request_type: type, existing: object, duplicate: object) -> None:
        self.request_type = request_type
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(
            f"{_name(request_type)} already has a handler, {_name(existing)}; "
            f"cannot also register {_name(duplicate)}. A request has exactly one handler."
        )


class NotARequest(MediaryError, TypeError):
    """A handler was registered for a class that is neither a request nor a notification."""

    def __init__(self, cls: type) -> None:
        self.cls = cls
        super().__init__(
            f"{_name(cls)} is not a request. Decorate it with @request, or with @notification "
            "if it can have many handlers (subclasses must be decorated too)."
        )


class NotANotification(MediaryError, TypeError):
    """An object whose class isn't decorated with `@notification` was published."""

    def __init__(self, cls: type) -> None:
        self.cls = cls
        super().__init__(
            f"{_name(cls)} is not a notification. Decorate it with @notification, or send it "
            "with `send` if it is a request."
        )


class InvalidHandlerSignature(MediaryError, TypeError):
    """A handler doesn't have the shape mediary can call."""

    def __init__(self, handler: object, reason: str) -> None:
        self.handler = handler
        super().__init__(f"Invalid handler {_name(handler)}: {reason}")


class InvalidBehaviorSignature(MediaryError, TypeError):
    """A behavior doesn't have the shape mediary can call."""

    def __init__(self, behavior: object, reason: str) -> None:
        self.behavior = behavior
        super().__init__(f"Invalid behavior {_name(behavior)}: {reason}")


class HandlerTimeout(MediaryError, TimeoutError):
    """A `TimeoutBehavior` gave up waiting for the rest of the pipeline."""

    def __init__(self, message_type: type, seconds: float) -> None:
        self.message_type = message_type
        self.seconds = seconds
        super().__init__(f"{_name(message_type)} was not handled within {seconds:g}s")


class ScanError(MediaryError):
    """`Mediator.scan` found problems; `errors` holds every one of them.

    Nothing from the failed scan is registered.
    """

    def __init__(self, errors: Sequence[Exception]) -> None:
        self.errors = tuple(errors)
        lines = "".join(f"\n  - {type(error).__name__}: {error}" for error in self.errors)
        super().__init__(f"scan found {len(self.errors)} problem(s):{lines}")
