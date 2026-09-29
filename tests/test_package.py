import importlib
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pytest

import mediary


def test_version_comes_from_installed_metadata() -> None:
    assert mediary.__version__ == version("mediary")


def test_package_ships_py_typed_marker() -> None:
    assert (Path(mediary.__file__).parent / "py.typed").is_file()


def test_the_core_imports_none_of_the_extras() -> None:
    script = (
        "import sys, mediary, mediary.behaviors, mediary.cqrs, mediary.kinds, mediary.testing;"
        "extras = {'anyio', 'dishka', 'fastapi', 'opentelemetry', 'starlette', 'trio'};"
        "print(sorted(extras & set(sys.modules)))"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, check=True)
    assert result.stdout.decode().strip() == "[]"


def test_the_otel_integration_says_which_extra_it_needs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "opentelemetry", None)  # as if it weren't installed
    monkeypatch.delitem(sys.modules, "mediary.ext.otel", raising=False)
    with pytest.raises(ModuleNotFoundError, match=r"pip install mediary\[otel\]") as exc:
        importlib.import_module("mediary.ext.otel")
    assert exc.value.name == "opentelemetry"
