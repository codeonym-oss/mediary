import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import mediary


def test_version_comes_from_installed_metadata() -> None:
    assert mediary.__version__ == version("mediary")


def test_package_ships_py_typed_marker() -> None:
    assert (Path(mediary.__file__).parent / "py.typed").is_file()


def test_the_core_imports_none_of_the_extras() -> None:
    script = (
        "import sys, mediary, mediary.behaviors, mediary.cqrs, mediary.kinds, mediary.testing;"
        "print(sorted({'anyio', 'dishka', 'fastapi', 'starlette', 'trio'} & set(sys.modules)))"
    )
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, check=True)
    assert result.stdout.decode().strip() == "[]"
