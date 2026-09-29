"""The public API is what the API reference documents: the `__all__` of each public module."""

import ast
import importlib
import inspect
import pkgutil
import re
from pathlib import Path
from types import ModuleType

import pytest

import mediary

REFERENCE = Path(__file__).parent.parent / "docs" / "reference"

# `.. autoclass:: mediary.Mediator`, or a MyST directive such as ```{py:data} mediary.Next
_NAMED = re.compile(
    r"^(?:\.\. auto(?:class|function|exception|data)::|```\{py:\w+\})\s+([\w.]+)", re.MULTILINE
)
_AUTOMODULE = re.compile(r"^\.\. automodule::\s+([\w.]+)", re.MULTILINE)


def _public_modules() -> list[str]:
    found = [info.name for info in pkgutil.walk_packages(mediary.__path__, "mediary.")]
    public = [n for n in found if not any(part.startswith("_") for part in n.split("."))]
    return sorted(["mediary", *public])


PUBLIC_MODULES = _public_modules()


def _reference() -> tuple[dict[str, set[str]], set[str]]:
    """Return the names documented one by one, by module, and the modules documented whole."""
    named: dict[str, set[str]] = {}
    whole: set[str] = set()
    for page in REFERENCE.glob("*.md"):
        text = page.read_text()
        for dotted in _NAMED.findall(text):
            module, name = dotted.rsplit(".", 1)
            named.setdefault(module, set()).add(name)
        whole.update(_AUTOMODULE.findall(text))
    return named, whole


NAMED, WHOLE = _reference()


def _import(name: str) -> ModuleType:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:  # an integration whose extra isn't installed
        pytest.skip(f"{name} needs {exc.name}")


def _attribute_docs(module: ModuleType) -> set[str]:
    """Return the module-level names that have a docstring after their assignment."""
    tree = ast.parse(inspect.getsource(module))
    names: set[str] = set()
    for node, after in zip(tree.body, tree.body[1:], strict=False):
        documented = isinstance(after, ast.Expr) and isinstance(after.value, ast.Constant)
        if documented and isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _autodoc_documents(module: ModuleType, name: str) -> bool:
    """Whether ``automodule`` documents ``name``: autodoc skips members with no docstring."""
    obj = getattr(module, name)
    if inspect.isclass(obj):
        return bool(vars(obj).get("__doc__"))
    if callable(obj) and not hasattr(obj, "__origin__"):
        return bool(getattr(obj, "__doc__", None))
    return name in _attribute_docs(module)


def test_every_public_module_is_found() -> None:
    assert "mediary.cqrs" in PUBLIC_MODULES
    assert "mediary.ext.otel" in PUBLIC_MODULES
    assert not [m for m in PUBLIC_MODULES if "._" in m]


@pytest.mark.parametrize("name", PUBLIC_MODULES)
def test_the_reference_documents_exactly_the_public_names(name: str) -> None:
    module = _import(name)
    exported = getattr(module, "__all__", None)
    assert exported is not None, f"{name} has no __all__"
    documented = set(NAMED.get(name, set()))
    if name in WHOLE:
        documented |= {n for n in exported if _autodoc_documents(module, n)}
    assert documented == set(exported), (
        f"{name}: undocumented {sorted(set(exported) - documented)}, "
        f"documented but not public {sorted(documented - set(exported))}"
    )


def test_the_reference_documents_only_public_modules() -> None:
    assert set(NAMED) | WHOLE <= set(PUBLIC_MODULES)
