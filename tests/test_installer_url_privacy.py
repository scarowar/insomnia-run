import os
from pathlib import Path
import subprocess
import sys
import io
from urllib.error import HTTPError

import pytest


@pytest.mark.parametrize("separator", ["\uff0f", "\uff1a"])
def test_inso_redirect_hides_malformed_url_credentials(
    tmp_path, monkeypatch, capsys, separator
):
    project = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(project / "scripts"))
    import install_runtime
    import verify_inso_release

    credential = "CANARY_REDIRECT_SECRET_7921"
    redirect = f"https://user:{credential}@mirror.example{separator}private/archive"

    class Opener:
        def open(self, request, *, timeout):
            assert request.full_url == "https://github.com/archive"
            raise HTTPError(
                request.full_url, 302, "Found", {"Location": redirect}, io.BytesIO()
            )

    monkeypatch.setattr(install_runtime, "build_opener", lambda *args: Opener())
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("INSOMNIA_RUN_DOWNLOAD_TOKEN", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_inso_release.py",
            "--asset",
            "inso-linux-x64-99.0.0.tar.xz",
            "--inso-sha256",
            "a" * 64,
            "--cache-directory",
            str(tmp_path / "cache"),
            "--inso-archive",
            "https://github.com/archive",
        ],
    )
    with pytest.raises(SystemExit) as error:
        verify_inso_release.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert credential not in output.out + output.err
    assert "Downloads require an unambiguous HTTPS URL" in output.err


@pytest.mark.parametrize("script", ["verify_inso_release.py", "install_runtime.py"])
@pytest.mark.parametrize("source", ["archive", "token-origin"])
@pytest.mark.parametrize("separator", ["\uff0f", "\uff1a"])
def test_installer_cli_hides_malformed_url_credentials(
    tmp_path, script, source, separator
):
    project = Path(__file__).resolve().parents[1]
    credential = "CANARY_URL_SECRET_7921"
    location = f"https://user:{credential}@mirror.example{separator}private/archive"
    if script == "verify_inso_release.py":
        arguments = [
            "--asset",
            "inso-linux-x64-99.0.0.tar.xz",
            "--inso-sha256",
            "a" * 64,
            "--cache-directory",
            str(tmp_path / "cache"),
            "--inso-archive",
            location if source == "archive" else str(tmp_path / "local"),
        ]
    else:
        arguments = [
            "--project",
            str(project),
            "--venv",
            str(tmp_path / "venv"),
            "--runtime-bundle",
            location if source == "archive" else str(tmp_path / "local"),
            "--runtime-bundle-sha256",
            "a" * 64,
        ]
    arguments.extend(
        [
            "--download-token-origin",
            location if source == "token-origin" else "https://mirror.example",
        ]
    )
    result = subprocess.run(
        [
            sys.executable,
            str(project / "scripts" / script),
            *arguments,
            "--offline-install",
        ],
        env={
            **os.environ,
            "RUNNER_TEMP": str(tmp_path),
            "INSOMNIA_RUN_DOWNLOAD_TOKEN": credential,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert credential not in result.stderr
    assert "Traceback" not in result.stderr
    if script == "verify_inso_release.py":
        assert "Downloads require an unambiguous HTTPS URL" in result.stderr
    else:
        assert "Runtime installation failed: ValueError" in result.stderr
