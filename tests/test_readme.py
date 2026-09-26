"""Run every Python example in the README, in order, as one program.

A block preceded by `<!-- file: path/to/module.py -->` is written to that path, on sys.path,
before anything runs. The other blocks run in one shared module, with top-level `await`, and
any `test_*` function a block defines is called with a fresh `RecordingMediator`.
"""

import ast
import inspect
import re
import sys
import types
from pathlib import Path

import pytest

from mediary.testing import RecordingMediator

README = Path(__file__).parent.parent / "README.md"
BLOCK = re.compile(r"(?:<!-- file: (?P<file>\S+) -->\n)?```python\n(?P<code>.*?)^```", re.S | re.M)


async def test_the_readme_examples_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    text = README.read_text()
    scripts: list[str] = []
    for match in BLOCK.finditer(text):
        # Pad with blank lines so tracebacks point at README line numbers.
        code = "\n" * text.count("\n", 0, match.start("code")) + match["code"]
        if match["file"]:
            path = tmp_path / match["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            (path.parent / "__init__.py").touch()
            path.write_text(match["code"])
        else:
            scripts.append(code)
    assert len(scripts) >= 9, "the README examples weren't found"

    monkeypatch.syspath_prepend(tmp_path)  # pyright: ignore[reportUnknownMemberType]
    readme = types.ModuleType("readme")
    monkeypatch.setitem(sys.modules, "readme", readme)
    try:
        for code in scripts:
            before = set(vars(readme))
            compiled = compile(code, str(README), "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
            result = eval(compiled, vars(readme))
            if inspect.iscoroutine(result):
                await result
            for name in sorted(set(vars(readme)) - before):
                if name.startswith("test_"):
                    await getattr(readme, name)(RecordingMediator())
    finally:
        for name in [m for m in sys.modules if m == "shop" or m.startswith("shop.")]:
            del sys.modules[name]
