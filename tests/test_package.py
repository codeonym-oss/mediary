from importlib.metadata import version
from pathlib import Path

import mediary


def test_version_comes_from_installed_metadata() -> None:
    assert mediary.__version__ == version("mediary")


def test_package_ships_py_typed_marker() -> None:
    assert (Path(mediary.__file__).parent / "py.typed").is_file()
