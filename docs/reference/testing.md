# `mediary.testing`

A recording mediator for tests; pytest provides one as the `mediator` fixture.

```{eval-rst}
.. automodule:: mediary.testing
```

## The pytest fixture

pytest loads `mediary.pytest_plugin` through its `pytest11` entry point whenever mediary is installed.

```{py:function} mediary.pytest_plugin.mediator()

A new, empty `RecordingMediator` for each test. Define a `mediator` fixture of your own, in a `conftest.py`, to register what every test needs or to pass a resolver.
```
