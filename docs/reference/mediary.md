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

## Errors

Every error mediary raises is a `MediaryError`.

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
.. autoexception:: mediary.NotARequest
```

```{eval-rst}
.. autoexception:: mediary.NotANotification
```

```{eval-rst}
.. autoexception:: mediary.InvalidHandlerSignature
```

```{eval-rst}
.. autoexception:: mediary.InvalidBehaviorSignature
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
