import json

from insomnia_run.action_runtime import convenience_json, split_list, write_outputs


def test_list_trimming_preserves_quotes_backslashes_and_internal_spaces():
    assert split_list("  a' b  , \\path\\  ") == ["a' b", "\\path\\"]


def test_convenience_json_is_valid_complete_and_bounded_in_utf16():
    small = json.dumps({"x": "ok"})
    assert convenience_json(small, requested=True) == (small, False)
    assert convenience_json(small, requested=False) == ("", False)
    large = json.dumps({"x": "\U0001f600" * 20000}, ensure_ascii=False)
    assert convenience_json(large, requested=True) == ("", True)


def test_outputs_cannot_inject_another_output(tmp_path):
    path = tmp_path / "output"
    write_outputs(path, {"markdown": "a\nexit-code=0\n", "exit-code": "3"})
    lines = path.read_text().splitlines()
    delimiter = lines[0].split("<<")[1]
    assert lines[0] == "markdown<<" + delimiter
    assert lines[4] == delimiter
    assert lines[5].startswith("exit-code<<")
