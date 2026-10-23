import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from insomnia_run.models import InsoCollectionOptions
from insomnia_run.runner import InsoRunner


@pytest.mark.parametrize("version", ["12.2.0", "12.6.0", "13.1.0", "13.3.1"])
def test_verified_bundled_version_does_not_start_a_help_process(monkeypatch, version):
    calls = []

    def execute(cmd, timeout):
        calls.append(cmd)
        assert "--help" not in cmd
        Path(cmd[cmd.index("--output") + 1]).write_text(json.dumps({"executions": []}))
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(execute))
    report = InsoRunner(verified_version=version).run_collection(
        InsoCollectionOptions(working_dir="fixture")
    )
    assert report.complete
    assert report.source == "native"
    assert len(calls) == 1


@pytest.mark.parametrize("version", [None, "11.0.0", "13.3.2", "unknown"])
def test_unknown_version_keeps_capability_discovery(monkeypatch, version):
    calls = []

    def execute(cmd, timeout):
        calls.append(cmd)
        return CompletedProcess(cmd, 0, "  --output <file>\n", "")

    monkeypatch.setattr(InsoRunner, "_run_command", staticmethod(execute))
    assert InsoRunner(verified_version=version)._supports_native_report()
    assert calls == [["inso", "run", "collection", "--help"]]


def test_output_capability_accepts_a_short_option_alias(monkeypatch):
    monkeypatch.setattr(
        InsoRunner,
        "_run_command",
        staticmethod(
            lambda cmd, timeout: CompletedProcess(cmd, 0, "  -o, --output <file>\n", "")
        ),
    )
    assert InsoRunner()._supports_native_report()
