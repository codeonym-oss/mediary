"""The exceptions mediary raises about messages, handlers and behaviors: ``MediaryError``s."""

from collections.abc import Sequence

from ._deprecation import attribute


def _name(obj: object) -> str:
    return f"{getattr(obj, '__module__', '?')}.{getattr(obj, '__qualname__', obj)}"


class MediaryError(Exception):
    """Base class for the errors mediary raises about messages, handlers and behaviors.

    An invalid argument, such as a negative ``RetryBehavior(max_retries=...)``, raises a plain
    ``ValueError`` or ``TypeError`` instead.
    """


class HandlerNotFound(MediaryError, LookupError):
    """No handler is registered for the type of the message that was sent or streamed."""

    request_type = attribute("request_type", "message_type")

    def __init__(self, message_type: type) -> None:
        self.message_type = message_type
        super().__init__(
            f"No handler registered for {_name(message_type)}. Is the class decorated with "
            "@request, and is its handler registered with this mediator?"
        )


class DuplicateHandler(MediaryError, ValueError):
    """A second handler was registered for a message type that has exactly one."""

    request_type = attribute("request_type", "message_type")

    def __init__(self, message_type: type, existing: object, duplicate: object) -> None:
        self.message_type = message_type
        self.existing = existing
        self.duplicate = duplicate
        super().__init__(
            f"{_name(message_type)} already has a handler, {_name(existing)}; "
            f"cannot also register {_name(duplicate)}. A request has exactly one handler."
        )


class NotAMessage(MediaryError, TypeError):
    """A handler was registered for a class that isn't decorated as a kind of message."""

    cls = attribute("cls", "message_type")

    def __init__(self, message_type: type) -> None:
        self.message_type = message_type
        super().__init__(
            f"{_name(message_type)} is not a message. Decorate it with @request, or with "
            "@notification if it can have many handlers (subclasses must be decorated too)."
        )


class NotANotification(MediaryError, TypeError):
    """A message was published whose kind isn't published, such as a request."""

    cls = attribute("cls", "message_type")

    def __init__(self, message_type: type) -> None:
        self.message_type = message_type
        super().__init__(
            f"{_name(message_type)} is not a notification. Decorate it with @notification, or "
            "send it with `send` if it is a request."
        )


class InvalidHandler(MediaryError, TypeError):
    """A handler can't be called by mediary: it has the wrong shape, or unresolvable hints.

    ``reason`` says why, as the message does after the handler's name.
    """

    def __init__(self, handler: object, reason: str) -> None:
        self.handler = handler
        self.reason = reason
        super().__init__(f"Invalid handler {_name(handler)}: {reason}")


class InvalidBehavior(MediaryError, TypeError):
    """A behavior can't be called by mediary: it has the wrong shape, or unresolvable hints.

    ``reason`` says why, as the message does after the behavior's name.
    """

    def __init__(self, behavior: object, reason: str) -> None:
        self.behavior = behavior
        self.reason = reason
        super().__init__(f"Invalid behavior {_name(behavior)}: {reason}")


class RuleViolation(MediaryError, TypeError):
    """A handler breaks a rule of its message's kind, such as a query handler returning None.

    ``kind`` is the name of the kind, ``reason`` the rule's explanation, and ``message_type``
    the message the handler was registered for (None when that isn't known).
    """

    def __init__(
        self, handler: object, kind: str, reason: str, message_type: type | None = None
    ) -> None:
        self.handler = handler
        self.kind = kind
        self.reason = reason
        self.message_type = message_type
        super().__init__(f"Handler {_name(handler)} breaks a rule of @{kind}: {reason}")


class HandlerTimeout(MediaryError, TimeoutError):
    """A ``TimeoutBehavior`` gave up waiting for the rest of the pipeline."""

    def __init__(self, message_type: type, seconds: float) -> None:
        self.message_type = message_type
        self.seconds = seconds
        super().__init__(f"{_name(message_type)} was not handled within {seconds:g}s")


class ScanError(MediaryError):
    """``Mediator.scan`` found problems; ``errors`` holds every one of them.

    Nothing from the failed scan is registered.
    """

    def __init__(self, errors: Sequence[Exception]) -> None:
        self.errors = tuple(errors)
        lines = "".join(f"\n  - {type(error).__name__}: {error}" for error in self.errors)
        super().__init__(f"scan found {len(self.errors)} problem(s):{lines}")
