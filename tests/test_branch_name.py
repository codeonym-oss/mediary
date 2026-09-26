import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_branch_name", Path(__file__).parents[1] / "scripts" / "check_branch_name.py"
)
assert _spec is not None
assert _spec.loader is not None
check_branch_name = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_branch_name)


@pytest.mark.parametrize(
    "branch",
    [
        "feat/5-package-scan",
        "fix/23-duplicate-handler-message",
        "chore/3-governance",
        "ci/4-release",
        "main",
        "release-please--branches--main",
        "dependabot/uv/ruff-0.17.0",
        "dependabot/github_actions/actions/checkout-8",
    ],
)
def test_accepts(branch: str) -> None:
    assert check_branch_name.main([branch]) == 0


@pytest.mark.parametrize(
    "branch",
    [
        "1-scaffold-project",  # no type
        "feature/5-scan",  # unknown type
        "feat/package-scan",  # no issue
        "feat/0-scan",  # issue numbers start at 1
        "feat/5-Package-Scan",  # uppercase
        "feat/5-package_scan",  # underscore
        "feat/5-",  # empty slug
        "feat/5-scan/extra",  # nested
    ],
)
def test_rejects_with_guidance(branch: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert check_branch_name.main([branch]) == 1
    assert "<type>/<issue>-<slug>" in capsys.readouterr().err
