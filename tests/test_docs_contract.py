from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
USER_MARKDOWN_FILES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
ISSUE_TEMPLATE_FILES = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))


def user_facing_text() -> str:
    return "\n".join(
        path.read_text() for path in [*USER_MARKDOWN_FILES, *ISSUE_TEMPLATE_FILES]
    )


def test_docs_do_not_contain_stale_versions():
    text = user_facing_text()

    assert "v0.1.0" not in text
    assert "12.2.0" not in text


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


def test_docs_do_not_force_moving_major_action_ref():
    text = user_facing_text()

    assert not re.search(r"scarowar/insomnia-run@v0(?!\.)", text)
    assert "scarowar/insomnia-run@v0.2.0" in text


def test_migration_page_is_in_navigation():
    migration = (ROOT / "docs" / "migration.md").read_text()
    nav = (ROOT / "mkdocs.yml").read_text()

    assert "v0.1.x to v0.2.0" in migration
    assert "migration.md" in nav


def test_inso_config_auto_detection_is_documented():
    reference = (ROOT / "docs" / "reference" / "inputs.md").read_text()
    migration = (ROOT / "docs" / "migration.md").read_text()
    action = (ROOT / "action.yml").read_text()

    assert ".insorc" in reference
    assert ".insorc" in migration
    assert "config-file" not in action
