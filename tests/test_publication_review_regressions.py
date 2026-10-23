import pytest

from test_publication import FakeTransport, old_comment, publish
from test_publication import context as context
from test_publication import scope as scope


@pytest.mark.parametrize(
    ("viewer_login", "comment_login"),
    [
        ("github-actions", "github-actions[bot]"),
        ("github-actions[bot]", "github-actions"),
    ],
)
def test_bot_login_suffix_difference_updates_same_numeric_author(
    context, scope, viewer_login, comment_login
):
    transport = FakeTransport(
        context,
        [[old_comment(scope, user={"id": 42, "login": comment_login})]],
    )
    transport.author = {"databaseId": 42, "login": viewer_login}

    result = publish(context, scope, transport)

    assert result.outputs() == {"comment-status": "updated", "comment-id": "123"}
    assert transport.calls[-1][0] == "PATCH"
    assert transport.calls[-1][1].endswith("/issues/comments/123")
    assert not any(
        method == "POST" and "/issues/" in url
        for method, url, _headers, _payload in transport.calls
    )


def test_bot_login_suffix_matching_cannot_override_numeric_author_mismatch(
    context, scope
):
    transport = FakeTransport(
        context,
        [[old_comment(scope, user={"id": 99, "login": "github-actions[bot]"})]],
    )
    transport.author = {"databaseId": 42, "login": "github-actions"}

    result = publish(context, scope, transport)

    assert result.status == "created"
    assert not any(call[0] == "PATCH" for call in transport.calls)


@pytest.mark.parametrize(
    "generation",
    ["nonsense", "0:1", "01:1", "9" * 1000 + ":1"],
    ids=["invalid", "zero", "leading-zero", "oversized"],
)
@pytest.mark.parametrize("has_valid_comment", [False, True])
def test_malformed_owned_generation_does_not_abort_comment_publication(
    context, scope, generation, has_valid_comment
):
    comments = [old_comment(scope, generation, id=456)]
    if has_valid_comment:
        comments.append(old_comment(scope))
    transport = FakeTransport(context, [comments])

    result = publish(context, scope, transport)

    assert result.status == ("updated" if has_valid_comment else "created")
    assert result.warning == ""
    assert result.comment_id == "123"
    assert transport.calls[-1][0] == ("PATCH" if has_valid_comment else "POST")
    if has_valid_comment:
        assert transport.calls[-1][1].endswith("/issues/comments/123")
    assert not any(
        method == "PATCH" and url.endswith("/issues/comments/456")
        for method, url, _headers, _payload in transport.calls
    )
