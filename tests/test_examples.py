"""Run the Python examples of the README and of each docs page, a page at a time.

A page's examples run in order, as one program. A block preceded by `<!-- file: pkg/mod.py -->`,
or whose fence has a `title="pkg/mod.py"`, is written to that path, on sys.path, before
anything runs. The other blocks run in one shared module, with top-level `await`, and any
`test_*` function a block defines is called with a fresh `RecordingMediator`. A block preceded
by `<!-- requires: module,... -->` runs only when those modules (extras) are installed.
"""

import ast
import importlib.util
import inspect
import re
import sys
import types
from pathlib import Path

import anyio
import pytest

from mediary.testing import RecordingMediator

ROOT = Path(__file__).parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
BLOCK = re.compile(
    r"(?:<!-- (?P<directive>file|requires): (?P<arg>\S+) -->\n)?"
    r'```python(?: title="(?P<title>[^"]+)")?\n(?P<code>.*?)^```',
    re.S | re.M,
)


def test_the_readme_and_the_docs_have_examples() -> None:
    assert len(BLOCK.findall((ROOT / "README.md").read_text())) >= 9
    assert len(PAGES) > 10


def write_files(page: Path, root: Path) -> list[str]:
    """Write the page's file blocks under `root`; return its other blocks, to run in order."""
    text = page.read_text()
    scripts: list[str] = []
    for match in BLOCK.finditer(text):
        # Pad with blank lines so tracebacks point at the page's line numbers.
        code = "\n" * text.count("\n", 0, match.start("code")) + match["code"]
        if match["directive"] == "requires" and not all(
            importlib.util.find_spec(module) for module in match["arg"].split(",")
        ):
            continue
        path = match["arg"] if match["directive"] == "file" else match["title"]
        if path is not None and path.endswith(".py"):
            file = root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            (file.parent / "__init__.py").touch()
            file.write_text(match["code"])
        else:
            scripts.append(code)
    return scripts


# The examples are written for asyncio (`python -m asyncio`), and define global kinds once.
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
@pytest.mark.parametrize("page", PAGES, ids=lambda page: str(page.relative_to(ROOT)))
async def test_the_examples_run(
    page: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripts = write_files(page, tmp_path)
    monkeypatch.syspath_prepend(tmp_path)  # pyright: ignore[reportUnknownMemberType]
    module = types.ModuleType("example")
    monkeypatch.setitem(sys.modules, "example", module)
    modules = set(sys.modules)
    try:
        for code in scripts:
            before = set(vars(module))
            compiled = compile(code, str(page), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            if compiled.co_flags & inspect.CO_COROUTINE:
                await eval(compiled, vars(module))
            else:  # as in a script: outside the event loop, where it may start its own
                await anyio.to_thread.run_sync(eval, compiled, vars(module))
            for name in sorted(set(vars(module)) - before):
                if name.startswith("test_"):
                    await getattr(module, name)(RecordingMediator())
    finally:
        for name in set(sys.modules) - modules:  # the page's own packages
            if str(tmp_path) in str(getattr(sys.modules[name], "__file__", "")):
                del sys.modules[name]
