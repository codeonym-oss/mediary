# `mediary`

The core: the mediator, the markers for messages and handlers, behaviors, and errors. Everything here is importable from `mediary`.

## Mediator

The mediator, and the streams it returns.

::: mediary.Mediator
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Stream
    options:
      heading_level: 3
      show_root_full_path: false

## Messages

Decorators and bases that declare messages and what they return.

::: mediary.request
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.notification
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.stream_request
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Returns
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Yields
    options:
      heading_level: 3
      show_root_full_path: false

## Handlers

::: mediary.handler
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Handler
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.StreamHandler
    options:
      heading_level: 3
      show_root_full_path: false

## Behaviors

::: mediary.behavior
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Behavior
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.StreamBehavior
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Next
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.NextStream
    options:
      heading_level: 3
      show_root_full_path: false

## Dependency injection

::: mediary.Resolver
    options:
      heading_level: 3
      show_root_full_path: false

## Publishing

::: mediary.PublishStrategy
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Sequential
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.Concurrent
    options:
      heading_level: 3
      show_root_full_path: false

## Retries

Mark errors as transient, for `RetryBehavior`.

::: mediary.retryable
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.TransientError
    options:
      heading_level: 3
      show_root_full_path: false

## Errors

Every error mediary raises is a `MediaryError`.

::: mediary.MediaryError
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.HandlerNotFound
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.DuplicateHandler
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.NotARequest
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.NotANotification
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.InvalidHandlerSignature
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.InvalidBehaviorSignature
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.RuleViolation
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.ScanError
    options:
      heading_level: 3
      show_root_full_path: false

::: mediary.HandlerTimeout
    options:
      heading_level: 3
      show_root_full_path: false
