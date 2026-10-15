from pathlib import Path
import shlex
import shutil
import subprocess

from packaging.requirements import Requirement
import pytest
import yaml

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


def test_ci_lockfile_gate_rejects_changed_metadata_without_rewriting(tmp_path):
    uv = shutil.which("uv")
    if not uv:
        pytest.skip("Lockfile verification requires uv")
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    step = next(
        step
        for step in workflow["jobs"]["lint"]["steps"]
        if step.get("name") == "Check lockfile freshness"
    )
    command = shlex.split(step["run"])
    assert command[0] == "uv"
    command[0] = uv
    command.append("--offline")
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(ROOT / name, tmp_path / name)
    original_lock = (tmp_path / "uv.lock").read_bytes()

    def check():
        return subprocess.run(
            command,
            cwd=tmp_path,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )

    current = check()
    assert current.returncode == 0, current.stderr
    project = tmp_path / "pyproject.toml"
    project.write_text(
        project.read_text()
        + '\n[project.optional-dependencies]\nfreshness-check = ["idna==3.10"]\n'
    )
    changed = check()
    assert changed.returncode != 0
    assert (tmp_path / "uv.lock").read_bytes() == original_lock
