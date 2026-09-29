"""The extension API for new kinds of message, such as the commands and queries of ``mediary.cqrs``.

A kind is a class decorator, like ``@request``, plus how its messages are dispatched and the
rules their handlers must follow. Handlers, behaviors, ``scan`` and ``LoggingBehavior`` work with
every kind, and behaviors can target one with ``kinds={"<name>"}``. ``handler_for`` and
``behavior_for`` make a kind's own ``@handler`` and ``@behavior``, which only work with its
messages.

Example:
    .. code-block:: python

        from mediary.kinds import HandlerInfo, define_kind

        def returns_a_report(info: HandlerInfo) -> str | None:
            if info.returns is not Report:
                return "it must be annotated to return a Report"
            return None

        report = define_kind("report", dispatch="send", rules=[returns_a_report])

"""

from ._behaviors import BehaviorDecorator, behavior_for
from ._handlers import HandlerDecorator, handler_for
from ._markers import Dispatch, HandlerInfo, HandlerRule, Kind, define_kind, kind_of

__all__ = [
    "BehaviorDecorator",
    "Dispatch",
    "HandlerDecorator",
    "HandlerInfo",
    "HandlerRule",
    "Kind",
    "behavior_for",
    "define_kind",
    "handler_for",
    "kind_of",
]
