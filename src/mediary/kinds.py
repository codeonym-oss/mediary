"""The extension API for new kinds of message, such as the commands and queries of `mediary.cqrs`.

A kind is a class decorator, like `@request`, plus how its messages are dispatched and the
rules their handlers must follow. Handlers, behaviors, `scan` and `LoggingBehavior` work with
every kind, and behaviors can target one with `kinds={"<name>"}`.

Example:
    ```python
    from mediary.kinds import HandlerInfo, define_kind

    def returns_a_report(info: HandlerInfo) -> str | None:
        if info.returns is not Report:
            return "it must be annotated to return a Report"
        return None

    report = define_kind("report", dispatch="send", rules=[returns_a_report])
    ```

"""

from ._markers import Dispatch, HandlerInfo, HandlerRule, Kind, define_kind, kind_of

__all__ = ["Dispatch", "HandlerInfo", "HandlerRule", "Kind", "define_kind", "kind_of"]
