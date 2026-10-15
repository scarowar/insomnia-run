from pathlib import Path

from packaging.requirements import Requirement
import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("package", "vulnerable", "patched"),
    [
        ("pymdown-extensions", "10.21.2", "11.0.1"),
        ("pymdown-extensions", "10.21.3", "11.0.1"),
        ("pymdown-extensions", "11.0.0", "11.0.1"),
        ("pytest", "9.0.2", "9.0.3"),
        ("pygments", "2.19.2", "2.20.0"),
    ],
)
def test_dependency_constraints_exclude_known_vulnerable_versions(
    package, vulnerable, patched
):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = [
        Requirement(entry)
        for group in project["dependency-groups"].values()
        for entry in group
        if isinstance(entry, str)
    ]
    requirement = next(item for item in requirements if item.name == package)
    assert vulnerable not in requirement.specifier
    assert patched in requirement.specifier

    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = next(item for item in lock["package"] if item["name"] == package)
    assert locked["version"] in requirement.specifier
