import json
import subprocess
import sys
import tracemalloc

import pytest

import insomnia_run.runner as runner
from insomnia_run.models import InsoCollectionOptions, InsoTestOptions
from insomnia_run.runner import InsoRunner


@pytest.mark.parametrize("streams", ["stdout", "stderr", "both"])
def test_process_capture_is_bounded_across_both_streams(monkeypatch, streams):
    monkeypatch.setattr(runner, "_MAX_CAPTURE_BYTES", 65536, raising=False)
    program = (
        "import os, time\n"
        f"streams = {streams!r}\n"
        "for index in range(1000):\n"
        "    for descriptor in ((1, 2) if streams == 'both' else (1,) if streams == 'stdout' else (2,)):\n"
        "        os.write(descriptor, b'x' * 4096)\n"
        "    time.sleep(0.001)\n"
    )
    tracemalloc.start()
    try:
        with pytest.raises(subprocess.SubprocessError, match="capture limit"):
            InsoRunner._run_command([sys.executable, "-c", program], 5)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 2 * 1024 * 1024


@pytest.mark.parametrize("native", [False, True])
def test_output_limit_discards_streams_and_keeps_only_valid_native_evidence(
    tmp_path, monkeypatch, native
):
    binary = tmp_path / "inso"
    payload = {
        "executions": [
            {
                "request": {"name": "GET orders", "_id": "req1"},
                "tests": [{"testCase": "completed", "status": "passed"}],
            }
        ]
    }
    binary.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, time\nfrom pathlib import Path\n"
        f"payload = {json.dumps(json.dumps(payload))}\n"
        "if '--output' in sys.argv:\n"
        "    Path(sys.argv[sys.argv.index('--output') + 1]).write_text(payload)\n"
        "os.write(1, b'1..1\\nok 1 - completed\\n')\n"
        "for index in range(1000):\n"
        "    os.write(2, b'PRIVATE_CAPTURE_CANARY' * 256)\n"
        "    time.sleep(0.001)\n"
    )
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(runner, "_MAX_CAPTURE_BYTES", 65536, raising=False)
    monkeypatch.setattr(InsoRunner, "_supports_native_report", lambda self: native)
    report = (
        InsoRunner().run_collection(InsoCollectionOptions(working_dir="fixture"))
        if native
        else InsoRunner().run_test(InsoTestOptions(working_dir="fixture"))
    )
    assert report.exit_code == 3
    assert not report.complete
    assert report.run_error.kind == "execution"
    assert "capture limit" in report.run_error.message
    assert report.raw_output is None
    assert report.passed_count == int(native)
    assert "PRIVATE_CAPTURE_CANARY" not in report.model_dump_json()


def test_capability_output_limit_is_a_configuration_error(tmp_path, monkeypatch):
    binary = tmp_path / "inso"
    binary.write_text(f"#!{sys.executable}\nimport os\nos.write(1, b'x' * 65537)\n")
    binary.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(runner, "_MAX_CAPTURE_BYTES", 65536)
    inso_runner = InsoRunner()
    with pytest.raises(runner.InsoConfigurationError, match="capture limit"):
        inso_runner._supports_native_report()
