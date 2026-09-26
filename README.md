# mediary

Typed, decorator-driven mediator + CQRS for Python — handlers, pipelines and notifications discovered by package scan.

> Work in progress. See the [roadmap](https://github.com/orgs/codeonym-oss/projects/2).

## Development

Requires [uv](https://docs.astral.sh/uv/).

```sh
uv sync                        # create .venv with dev tools
uv run pre-commit install      # lint, format and typecheck on commit
uv run pytest                  # tests + coverage gate (95%)
uv run pyright                 # strict type checking
```
