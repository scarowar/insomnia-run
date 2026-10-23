import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from runtime_bundle import sha256_file, source_digest, verify_bundle


def refresh_bundle_metadata(root, project):
    wheels = sorted((root / "wheels").glob("*.whl"))
    requirements = root / "requirements.txt"
    requirements.write_text(
        "".join(
            f"{wheel.name.split('-')[0]}=={wheel.name.split('-')[1]} "
            f"--hash=sha256:{sha256_file(wheel)}\n"
            for wheel in wheels
        )
    )
    manifest = {
        "schema_version": 1,
        "source_sha256": source_digest(project),
        "lock_sha256": sha256_file(project / "uv.lock"),
        "python_tag": "cpython-310",
        "platform": "linux-x86_64",
        "application": "wheels/insomnia_run-0.2.0-py3-none-any.whl",
        "files": {
            path.relative_to(root).as_posix(): sha256_file(path)
            for path in [requirements, *wheels]
        },
    }
    (root / "manifest.json").write_text(json.dumps(manifest))


@pytest.fixture
def locked_bundle(tmp_path):
    project = tmp_path / "project"
    (project / "src/insomnia_run").mkdir(parents=True)
    (project / "src/insomnia_run/__init__.py").write_text("")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "insomnia-run"\nversion = "0.2.0"\n'
        'requires-python = ">=3.10"\n'
        'dependencies = ["alpha-dependency==1.0.0", "beta-dependency==1.0.0"]\n'
    )
    root = tmp_path / "bundle"
    (root / "wheels").mkdir(parents=True)
    (root / "wheels/insomnia_run-0.2.0-py3-none-any.whl").write_bytes(
        b"first-party application"
    )
    lock = (
        'version = 1\nrevision = 5\nrequires-python = ">=3.10"\n'
        '\n[[package]]\nname = "insomnia-run"\nversion = "0.2.0"\n'
        'source = { editable = "." }\n'
        'dependencies = [{ name = "alpha-dependency" }, { name = "beta-dependency" }]\n'
    )
    for name in ("alpha_dependency", "beta_dependency"):
        content = f"authentic {name} wheel".encode()
        filename = f"{name}-1.0.0-py3-none-any.whl"
        (root / "wheels" / filename).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        lock += (
            f'\n[[package]]\nname = "{name.replace("_", "-")}"\n'
            'version = "1.0.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            f'wheels = [{{ url = "https://files.pythonhosted.org/{filename}", '
            f'hash = "sha256:{digest}", size = {len(content)} }}]\n'
        )
    (project / "uv.lock").write_text(lock)
    refresh_bundle_metadata(root, project)
    return root, project


def test_dependency_wheels_matching_lockfile_are_accepted(locked_bundle):
    root, project = locked_bundle

    verified = verify_bundle(root, project, "cpython-310", "linux-x86_64")

    assert verified.application == root / "wheels/insomnia_run-0.2.0-py3-none-any.whl"


@pytest.mark.parametrize("dependency", ["alpha_dependency", "beta_dependency"])
def test_self_consistent_forged_dependency_hash_is_rejected(locked_bundle, dependency):
    root, project = locked_bundle
    wheel = root / "wheels" / f"{dependency}-1.0.0-py3-none-any.whl"
    wheel.write_bytes(b"forged dependency bytes")
    refresh_bundle_metadata(root, project)

    with pytest.raises(ValueError, match="lock|SHA-256"):
        verify_bundle(root, project, "cpython-310", "linux-x86_64")


@pytest.mark.parametrize("dependency", ["alpha_dependency", "beta_dependency"])
def test_dependency_filename_must_match_the_locked_asset(locked_bundle, dependency):
    root, project = locked_bundle
    wheel = root / "wheels" / f"{dependency}-1.0.0-py3-none-any.whl"
    wheel.rename(wheel.with_name(f"{dependency}-1.0.0-py310-none-any.whl"))
    refresh_bundle_metadata(root, project)

    with pytest.raises(ValueError, match="lock|wheel"):
        verify_bundle(root, project, "cpython-310", "linux-x86_64")


@pytest.mark.parametrize(
    "name", ["--offline", "project with spaces", "project;touch CANARY"]
)
def test_project_path_is_bound_as_one_option_value(locked_bundle, monkeypatch, name):
    root, project = locked_bundle
    destination = project.with_name(name)
    project.rename(destination)
    monkeypatch.chdir(destination.parent)
    relative_project = Path(name)

    verified = verify_bundle(root, relative_project, "cpython-310", "linux-x86_64")

    assert verified.application.is_file()
    assert not (destination.parent / "CANARY").exists()


def test_selected_uv_executable_is_never_interpreted_by_a_shell(
    locked_bundle, tmp_path, monkeypatch
):
    root, project = locked_bundle
    references = [
        {
            "type": "distribution",
            "url": f"https://files.pythonhosted.org/{wheel.name}",
            "hashes": [{"alg": "SHA-256", "content": sha256_file(wheel)}],
        }
        for wheel in (root / "wheels").glob("*.whl")
        if not wheel.name.startswith("insomnia_run-")
    ]
    export = json.dumps({"components": [{"externalReferences": references}]})
    executable = tmp_path / "uv;touch CANARY"
    executable.write_text(f"#!{sys.executable}\nprint({export!r})\n")
    executable.chmod(0o700)
    monkeypatch.chdir(tmp_path)

    verified = verify_bundle(
        root, project, "cpython-310", "linux-x86_64", uv=str(executable)
    )

    assert verified.application.is_file()
    assert not (tmp_path / "CANARY").exists()
