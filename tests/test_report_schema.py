import json
from pathlib import Path

from insomnia_run.models import InsoRunReport


ROOT = Path(__file__).resolve().parents[1]


def test_published_schema_matches_the_actual_public_model():
    schema = json.loads((ROOT / "schemas/report-v1.schema.json").read_text())
    assert schema.pop("$schema") == "https://json-schema.org/draft/2020-12/schema"
    schema.pop("$id")
    assert schema == InsoRunReport.model_json_schema()


def test_published_example_is_a_valid_report():
    report = InsoRunReport.model_validate_json(
        (ROOT / "schemas/examples/failed-collection.json").read_text()
    )
    assert report.schema_version == 1
    assert report.exit_code == 1
    assert report.request_count == 1
