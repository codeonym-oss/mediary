# `mediary`

The core: the mediator, the markers for messages and handlers, behaviors, and errors. Everything here is importable from `mediary`.

## Mediator

The mediator, and the streams it returns.

```{eval-rst}
.. autoclass:: mediary.Mediator
```

```{eval-rst}
.. autoclass:: mediary.Stream
```

The narrow views of a mediator that code can depend on instead:

```{eval-rst}
.. autoclass:: mediary.Sender
```

```{eval-rst}
.. autoclass:: mediary.Publisher
```

## Messages

Decorators and bases that declare messages and what they return.

```{eval-rst}
.. autofunction:: mediary.request
```

```{eval-rst}
.. autofunction:: mediary.notification
```

```{eval-rst}
.. autofunction:: mediary.stream_request
```

```{eval-rst}
.. autoclass:: mediary.Returns
```

```{eval-rst}
.. autoclass:: mediary.Yields
```

## Handlers

```{eval-rst}
.. autofunction:: mediary.handler
```

```{eval-rst}
.. autoclass:: mediary.Handler
```

```{eval-rst}
.. autoclass:: mediary.SyncHandler
```

```{eval-rst}
.. autoclass:: mediary.StreamHandler
```

## Behaviors

```{eval-rst}
.. autofunction:: mediary.behavior
```

```{eval-rst}
.. autoclass:: mediary.Behavior
```

```{eval-rst}
.. autoclass:: mediary.StreamBehavior
```

```{py:data} mediary.Next

Calls the rest of the pipeline (the next behavior, or the handler) and returns its result.

An alias of `Callable[[], Awaitable[R]]`.
```

```{py:data} mediary.NextStream

Opens the rest of a stream's pipeline (the next behavior, or the handler) as an iterator.

An alias of `Callable[[], AsyncIterator[R]]`.
```

## Dependency injection

```{eval-rst}
.. autoclass:: mediary.Resolver
```

## Publishing

```{eval-rst}
.. autoclass:: mediary.PublishStrategy
```

```{eval-rst}
.. autoclass:: mediary.NotificationCall
```

```{eval-rst}
.. autoclass:: mediary.Sequential
```

```{eval-rst}
.. autoclass:: mediary.Concurrent
```

## Retries

Mark errors as transient, for `RetryBehavior`.

```{eval-rst}
.. autofunction:: mediary.retryable
```

```{eval-rst}
.. autoexception:: mediary.TransientError
```

## Version

```{py:data} mediary.__version__

The installed version of mediary, such as `"0.3.0"`.
```

## Errors

Every error mediary raises about messages, handlers and behaviors is a `MediaryError`, and also the closest built-in exception, such as `LookupError` or `TypeError`. An invalid argument raises a plain `ValueError` or `TypeError`.

```{eval-rst}
.. autoexception:: mediary.MediaryError
```

```{eval-rst}
.. autoexception:: mediary.HandlerNotFound
```

```{eval-rst}
.. autoexception:: mediary.DuplicateHandler
```

```{eval-rst}
.. autoexception:: mediary.NotAMessage
```

```{eval-rst}
.. autoexception:: mediary.NotANotification
```

```{eval-rst}
.. autoexception:: mediary.InvalidHandler
```

```{eval-rst}
.. autoexception:: mediary.InvalidBehavior
```

```{eval-rst}
.. autoexception:: mediary.RuleViolation
```

```{eval-rst}
.. autoexception:: mediary.ScanError
```

```{eval-rst}
.. autoexception:: mediary.HandlerTimeout
```

## Deprecated

These names still work, with a `DeprecationWarning` that names the replacement, and will be removed in 1.0.

| Deprecated | Use |
|---|---|
| `NotARequest` | `NotAMessage` |
| `InvalidHandlerSignature` | `InvalidHandler` |
| `InvalidBehaviorSignature` | `InvalidBehavior` |
| `.cls` of `NotAMessage` and `NotANotification` | `.message_type` |
| `.request_type` of `HandlerNotFound` and `DuplicateHandler` | `.message_type` |
| `Mediator.register(request_type=..., handler=...)` | `register(message_type, handler)`: both are positional-only |
| `RecordingMediator.sent_of(request_type=...)`, `published_of(notification_type=...)`, `streamed_of(request_type=...)` | pass the type positionally |
