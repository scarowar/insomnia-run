import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
# docs/agents is local-only and excluded from user-facing checks.
USER_MARKDOWN_FILES = [
    ROOT / "README.md",
    *sorted(path for path in (ROOT / "docs").rglob("*.md") if "agents" not in path.parts),
]
ACTION_REF_RE = re.compile(r"scarowar/insomnia-run@v\d+\.\d+\.\d+")


def user_facing_text() -> str:
    return "\n".join(path.read_text() for path in USER_MARKDOWN_FILES)


def test_docs_inso_version_default_matches_action():
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    default = action["inputs"]["inso-version"]["default"]
    reference = (ROOT / "docs" / "reference" / "inputs.md").read_text()

    assert f"`{default}`" in reference
    assert "12.2.0" not in user_facing_text()


def test_docs_do_not_contain_internal_process_language():
    text = user_facing_text().lower()

    for phrase in [
        "conversation",
        "terraform-branch-deploy",
        "tbd",
        "north star",
        "best unofficial",
        "release-ready",
        "enterprise-ready",
        "audit-backed",
        "for now",
        "future work",
        "deferred",
    ]:
        assert phrase not in text


def test_docs_pin_exact_action_refs_never_moving_ones():
    text = user_facing_text()

    assert not re.search(r"scarowar/insomnia-run@v0(?!\.)", text)
    assert not re.search(r"scarowar/insomnia-run@(main|master|develop)\b", text)
    refs = re.findall(r"scarowar/insomnia-run@(\S+)", text)
    assert refs, "docs should reference the action"
    for ref in refs:
        assert ACTION_REF_RE.fullmatch(f"scarowar/insomnia-run@{ref}"), ref
