"""Marking exceptions as transient, so that ``RetryBehavior`` retries them."""

from typing import Final, TypeVar

_E = TypeVar("_E", bound=type[Exception])

_RETRYABLE_ATTR: Final = "__mediary_retryable__"


def retryable(cls: _E) -> _E:
    """Mark an exception class as transient, so that ``RetryBehavior`` retries it.

    Subclasses are retryable too, so marking a base marks a whole family of errors. For
    exceptions you can't decorate, such as built-in or third-party ones, pass them to
    ``RetryBehavior(retry_on=...)`` instead.

    Example:
        .. code-block:: python

            @retryable
            class PaymentGatewayUnavailable(Exception):
                pass

    Raises:
        TypeError: ``cls`` isn't an ``Exception`` subclass, or it is a built-in one.

    """
    if not _is_exception_class(cls):
        raise TypeError(f"@retryable decorates exception classes, not {cls!r}")
    try:
        setattr(cls, _RETRYABLE_ATTR, True)
    except TypeError:
        raise TypeError(
            f"{cls.__qualname__} can't be decorated; retry it with "
            f"RetryBehavior(retry_on=({cls.__qualname__},)) instead"
        ) from None
    return cls


def _is_exception_class(obj: object) -> bool:
    # Typed as `object`: the bound on `retryable` isn't enforced for untyped callers.
    return isinstance(obj, type) and issubclass(obj, Exception)


def is_retryable(error: BaseException) -> bool:
    """Whether the class of ``error``, or one of its bases, is marked ``@retryable``."""
    return getattr(type(error), _RETRYABLE_ATTR, False) is True


@retryable
class TransientError(Exception):
    """Base for errors that may go away on their own, so retrying makes sense.

    Subclasses are retried by ``RetryBehavior``, like any exception marked ``@retryable``.

    Example:
        .. code-block:: python

            class RateLimited(TransientError):
                pass

    """
