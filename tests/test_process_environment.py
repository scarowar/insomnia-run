"""Only supported runtime configuration crosses the Inso process boundary."""

import json
import os
import sys

from hypothesis import given, settings, strategies as st
import pytest

from insomnia_run.models import InsoCollectionOptions
from insomnia_run.runner import InsoRunner


def child_environment(parent):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(os, "environ", dict(parent))
        before = dict(os.environ)
        result = InsoRunner._run_command(
            [
                sys.executable,
                "-c",
                "import json,os; print(json.dumps(dict(os.environ)))",
            ],
            10,
        )
        assert result.returncode == 0
        assert dict(os.environ) == before
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "name",
    [
        "DOCKER_AUTH_CONFIG",
        "SSH_AUTH_SOCK",
        "CUSTOM_COLLECTION_REGION",
        "ORDINARY_BUILD_FLAG",
        "API_BASE_URL",
        "FUTURE_VENDOR_SESSION_MATERIAL",
    ],
)
def test_unlisted_variables_are_absent_without_credential_name_patterns(name):
    child = child_environment({"PATH": os.defpath, name: "synthetic-private-value"})
    assert name not in child


@settings(max_examples=12, deadline=None)
@given(suffix=st.text(alphabet="0123456789ABCDEF", min_size=8, max_size=24))
def test_future_unknown_variable_names_are_denied_by_default(suffix):
    name = "FUTURE_CONFIG_" + suffix
    child = child_environment({"PATH": os.defpath, name: "synthetic-future-value"})
    assert name not in child


def test_supported_runtime_network_and_public_github_configuration_survives(tmp_path):
    parent = {
        "PATH": os.defpath,
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "HTTPS_PROXY": "http://proxy.example.invalid:8080",
        "SSL_CERT_FILE": str(tmp_path / "certificates.pem"),
        "NODE_EXTRA_CA_CERTS": str(tmp_path / "node-certificates.pem"),
        "GITHUB_WORKSPACE": str(tmp_path / "workspace"),
        "GITHUB_SHA": "a" * 40,
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_REPOSITORY": "example/collection",
    }
    child = child_environment(parent)
    for name, value in parent.items():
        assert child[name] == value
    assert child["INSO_TELEMETRY_DISABLED"] == "1"


@pytest.mark.parametrize(
    "name",
    [
        "LC_FUTURE_CONFIGURATION",
        "LC_PRIVATE_SESSION",
        "GITHUB_FUTURE_CONTEXT",
        "GITHUB_UNKNOWN_PUBLIC_VALUE",
        "GITHUB_ENV",
        "GITHUB_PATH",
        "GITHUB_OUTPUT",
        "GITHUB_STEP_SUMMARY",
        "GITHUB_STATE",
    ],
)
def test_namespace_extensions_and_workflow_control_paths_are_not_inherited(name):
    child = child_environment({"PATH": os.defpath, name: "/tmp/synthetic-control-path"})
    assert name not in child


@pytest.mark.parametrize(
    "name",
    [
        "LD_PRELOAD",
        "LD_LIBRARY_PATH",
        "DYLD_INSERT_LIBRARIES",
        "NODE_OPTIONS",
        "PYTHONPATH",
    ],
)
def test_startup_injection_settings_are_not_inherited(name):
    child = child_environment(
        {"PATH": os.defpath, name: "/nonexistent/insomnia-synthetic-startup-value"}
    )
    assert name not in child


@pytest.mark.parametrize("setting", [None, "", "0", "false", "parent-value", "1"])
def test_telemetry_is_always_disabled_without_modifying_parent(setting):
    parent = {"PATH": os.defpath, "UNKNOWN_CONFIGURATION": "synthetic-value"}
    if setting is not None:
        parent["INSO_TELEMETRY_DISABLED"] = setting
    before = dict(parent)
    child = child_environment(parent)
    assert child["INSO_TELEMETRY_DISABLED"] == "1"
    assert parent == before


def test_explicit_collection_overrides_cross_as_arguments_not_ambient_environment(
    tmp_path, monkeypatch
):
    binary = tmp_path / "inso"
    binary.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:]\n"
        "print(json.dumps({'args':args,'custom':os.environ.get('CUSTOM_COLLECTION_VALUE')}))\n"
        "native={'executions':[{'request':{'_id':'req_one','name':'GET orders'},'response':{'code':200},'tests':[{'testCase':'explicit overrides','status':'passed'}]}]}\n"
        "Path(args[args.index('--output')+1]).write_text(json.dumps(native))\n"
        "print('1..1\\nok 1 - explicit overrides')\n"
    )
    binary.chmod(0o755)
    parent = {
        "PATH": str(tmp_path),
        "HOME": str(tmp_path),
        "CUSTOM_COLLECTION_VALUE": "ambient-value",
    }
    monkeypatch.setattr(os, "environ", dict(parent))
    overrides = [
        "CUSTOM_COLLECTION_VALUE=first-explicit",
        "CUSTOM_COLLECTION_VALUE=last-explicit",
    ]
    report = InsoRunner(verified_version="13.3.1").run_collection(
        InsoCollectionOptions(
            working_dir=str(tmp_path / "collection.yaml"), env_var=overrides
        )
    )
    assert report.exit_code == 0
    recorded = json.loads(report.raw_output.splitlines()[0])
    assert recorded["custom"] is None
    args = recorded["args"]
    assert [
        args[index + 1]
        for index, argument in enumerate(args)
        if argument == "--env-var"
    ] == overrides
    assert dict(os.environ) == parent
