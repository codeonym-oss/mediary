# `mediary.kinds`

Define kinds of message of your own, with rules for their handlers.

```{eval-rst}
.. automodule:: mediary.kinds
```

```{py:data} mediary.kinds.Dispatch

How messages of a kind are dispatched: `"send"`, `"publish"` or `"stream"`.

An alias of `Literal["send", "publish", "stream"]`.
```

```{py:data} mediary.kinds.HandlerRule

Checks a handler of a kind: returns why it can't be registered, or `None` if it can.

An alias of `Callable[[HandlerInfo], str | None]`.
```
