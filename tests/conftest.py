import importlib
import sys
import textwrap
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

pytest_plugins = ["pytester", "mediary.pytest_plugin"]

MakePackage = Callable[[dict[str, str]], str]


@pytest.fixture
def make_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MakePackage]:
    """Write a uniquely named package from `{relative path: source}` and return its name."""
    monkeypatch.syspath_prepend(tmp_path)  # pyright: ignore[reportUnknownMemberType]
    names: list[str] = []

    def make(files: dict[str, str]) -> str:
        name = f"scanned_{uuid.uuid4().hex}"
        names.append(name)
        root = tmp_path / name
        for relative, source in {"__init__.py": "", **files}.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            for package in [path.parent, *path.parent.parents]:
                if package == tmp_path:
                    break
                (package / "__init__.py").touch()
            path.write_text(textwrap.dedent(source))
        importlib.invalidate_caches()
        return name

    yield make
    for module in list(sys.modules):
        if module.split(".")[0] in names:
            del sys.modules[module]
