# Stability

mediary is in **Beta**: its API is settled, and changes to it follow the policy below. The policy applies to every release from 0.3 on.

## The public API

The public API is what the [API reference](reference/mediary.md) documents. It is exactly the names in the `__all__` of these modules, and a test checks that the reference and `__all__` agree:

- `mediary`
- `mediary.cqrs`
- `mediary.kinds`
- `mediary.behaviors`
- `mediary.testing`, and the pytest fixture `mediator`
- `mediary.ext.dishka`, `mediary.ext.fastapi` and `mediary.ext.otel`

The public API also includes what these documented names do:
- their signatures, return types and errors;
- the `extra` field names of `LoggingBehavior`'s log records;
- the span names and attributes of `TracingBehavior`.

These are **not** part of the public API, and can change in any release:

- any module or name that starts with `_`, such as `mediary._markers`, even when you can import it;
- a name that a public module imports but doesn't list in its `__all__`;
- the attributes that mediary's decorators set on classes and functions;
- the wording of error messages and log messages;
- the order of handlers and behaviors, except where the reference documents it.

## Breaking changes

A change is **breaking** when code that uses the public API as documented can stop working or stop type checking. Examples:
- removing or renaming a public name, a parameter or an attribute;
- making a parameter required, or positional-only, or keyword-only;
- accepting fewer arguments or types than before;
- raising an error that isn't a subclass of the one documented before;
- adding a method to a protocol that your code implements, such as `Resolver`, `PublishStrategy`, `Sender` or `Publisher`;
- changing documented behavior.

These are **not** breaking:
- adding a public name, an optional parameter, or a new kind of message;
- accepting more types than before;
- raising a subclass of a documented error;
- fixing a bug, even one that code relied on;
- a type hint that catches a real error the old hint missed.

Versions follow [Semantic Versioning](https://semver.org/):

| | A breaking change needs | New features come in |
|---|---|---|
| **Before 1.0** (0.x) | a minor release, and only through a deprecation first | a minor release |
| **From 1.0** | a major release | a minor release |

Fixes come in patch releases. The [changelog](changelog.md) lists every deprecation and breaking change.

## Deprecations

A name is deprecated before it is removed or renamed:

- It keeps working. Each use raises a `DeprecationWarning` that names its replacement, such as "mediary.NotARequest is deprecated and will be removed in 1.0; use mediary.NotAMessage".
- Type checkers flag it as deprecated, where they can (with `@deprecated`, [PEP 702](https://peps.python.org/pep-0702/)).
- The docs and examples use only its replacement. The API reference lists it only under "Deprecated".
- **Before 1.0**, it is removed in 1.0, not before. **From 1.0**, it is removed only in the next major release.

Python hides `DeprecationWarning` outside `__main__` by default, but pytest shows it. To make mediary's deprecation warnings errors in your tests, so none slip by, add this to your pytest configuration:

```toml
[tool.pytest.ini_options]
filterwarnings = ["error:.*will be removed in 1.0:DeprecationWarning"]
```

## Python support

mediary supports every CPython version from 3.11 that hasn't reached its [end of life](https://devguide.python.org/versions/). CI tests each one.

A Python version is dropped in the first minor release after its end of life, and the changelog says so. This isn't a breaking change: `requires-python` means pip and uv keep installing the last release that supports your Python. A new Python version is supported from the first release after it comes out.
