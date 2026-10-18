import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from insomnia_run.publication import (
    COMMENT_WARNING,
    ApiResponse,
    CommentContext,
    CommentGeneration,
    CommentScope,
    artifact_upload_supported,
    comment_marker,
    failure_annotations,
    github_api_url,
    publish_pr_comment,
)
from insomnia_run import publication


@pytest.fixture
def context():
    repository = {"id": 12, "full_name": "owner/project", "fork": False}
    return CommentContext(
        repository="owner/project",
        event_name="pull_request",
        actor="maintainer",
        event={
            "repository": repository,
            "number": 8,
            "pull_request": {
                "number": 8,
                "head": {"repo": repository},
                "base": {"repo": repository},
                "user": {"login": "maintainer"},
            },
        },
    )


@pytest.fixture
def scope():
    return CommentScope(
        workflow=".github/workflows/test.yml", job="api", matrix={"os": "linux"}
    )


class FakeTransport:
    def __init__(self, context, pages=None):
        self.pull = context.event["pull_request"]
        self.issue = {
            "id": 80,
            "number": 8,
            "url": "https://api.github.com/repos/owner/project/issues/8",
            "repository_url": "https://api.github.com/repos/owner/project",
            "user": {"login": "maintainer"},
            "pull_request": {
                "url": "https://api.github.com/repos/owner/project/pulls/8"
            },
        }
        self.pages = pages or [[]]
        self.calls = []
        self.author = {"databaseId": 42, "login": "publisher[bot]"}

    def __call__(self, method, url, headers, body):
        payload = json.loads(body) if body else None
        self.calls.append((method, url, headers, payload))
        if url.endswith("/graphql"):
            return ApiResponse(200, {"data": {"viewer": self.author}})
        if "/pulls/" in url:
            return (
                ApiResponse(200, self.pull)
                if "pull_request" in self.issue
                else ApiResponse(404, None)
            )
        if url.lower().endswith("/repos/owner/project"):
            return ApiResponse(200, {"id": 12, "full_name": "owner/project"})
        if url.endswith("/repos/owner/project/issues/8"):
            return ApiResponse(200, self.issue)
        if method == "GET":
            page = int(url.rsplit("=", 1)[1])
            return ApiResponse(200, self.pages[page - 1])
        return ApiResponse(201 if method == "POST" else 200, {"id": 123})


def old_comment(scope, generation="1:1", **changes):
    comment = {
        "id": 123,
        "user": {"id": 42, "login": "publisher[bot]"},
        "body": f"{comment_marker(scope)}\n<!-- insomnia-run:generation:v1:{generation} -->\n\nold report",
    }
    return {**comment, **changes}


def publish(context, scope, transport, **kwargs):
    return publish_pr_comment(
        context=context,
        scope=scope,
        generation=CommentGeneration(2, 1),
        redacted_body="new report",
        token="test-instance-token",
        transport=transport,
        **kwargs,
    )


def test_creates_scoped_comment_and_returns_action_outputs(context, scope):
    transport = FakeTransport(context)
    result = publish(context, scope, transport)

    assert result.outputs() == {"comment-status": "created", "comment-id": "123"}
    assert result.warning == ""
    method, url, headers, payload = transport.calls[-1]
    assert method == "POST"
    assert url == "https://api.github.com/repos/owner/project/issues/8/comments"
    assert headers["Authorization"] == "Bearer test-instance-token"
    assert payload == {
        "body": f"{comment_marker(scope)}\n<!-- insomnia-run:generation:v1:2:1 -->\n\nnew report"
    }


def test_replaces_whole_existing_comment(context, scope):
    transport = FakeTransport(context, [[old_comment(scope)]])
    result = publish(context, scope, transport)

    assert result.status == "updated"
    assert transport.calls[-1][0] == "PATCH"
    assert transport.calls[-1][1].endswith("/issues/comments/123")
    assert "old report" not in transport.calls[-1][3]["body"]


def test_searches_all_pages_before_updating(context, scope):
    unrelated = {"id": 1, "body": "other", "user": {"id": 42}}
    transport = FakeTransport(context, [[unrelated] * 100, [old_comment(scope)]])
    assert publish(context, scope, transport).status == "updated"
    pages = [call[1] for call in transport.calls if "per_page=" in call[1]]
    assert pages[0].endswith("per_page=100&page=1")
    assert pages[1].endswith("per_page=100&page=2")


@pytest.mark.parametrize(
    "body",
    [
        "prefix{marker}\n<!-- insomnia-run:generation:v1:1:1 -->",
        "{marker}suffix\n<!-- insomnia-run:generation:v1:1:1 -->",
        "report\n{marker}\n<!-- insomnia-run:generation:v1:1:1 -->",
        "```\n{marker}\n<!-- insomnia-run:generation:v1:1:1 -->\n```",
    ],
)
def test_does_not_match_embedded_or_spoofed_marker(context, scope, body):
    spoof = old_comment(scope, body=body.format(marker=comment_marker(scope)))
    transport = FakeTransport(context, [[spoof]])
    assert publish(context, scope, transport).status == "created"


@pytest.mark.parametrize(
    "user", [{"id": 99, "login": "publisher[bot]"}, {"id": 42, "login": "other"}, {}]
)
def test_never_overwrites_another_author(context, scope, user):
    transport = FakeTransport(context, [[old_comment(scope, user=user)]])
    assert publish(context, scope, transport).status == "created"


@pytest.mark.parametrize("generation", ["3:1", "2:2"])
def test_skips_stale_generation_without_a_write(context, scope, generation):
    transport = FakeTransport(context, [[old_comment(scope, generation)]])
    result = publish(context, scope, transport)
    assert result.outputs() == {"comment-status": "stale", "comment-id": "123"}
    assert not any(call[0] == "PATCH" for call in transport.calls)
    assert not any(
        call[0] == "POST" and not call[1].endswith("/graphql")
        for call in transport.calls
    )


def test_stale_generation_on_later_page_is_not_overwritten(context, scope):
    transport = FakeTransport(
        context, [[old_comment(scope)] * 100, [old_comment(scope, "9:1", id=456)]]
    )
    result = publish(context, scope, transport)
    assert result.status == "stale"
    assert result.comment_id == "456"


@pytest.mark.parametrize(
    "generation",
    [
        "0:1",
        "1:0",
        "01:1",
        "nonsense",
        "1:1 -->\nextra",
        "1:1 --> trailing",
        "9" * 1000 + ":1",
    ],
)
def test_owned_marker_with_invalid_generation_warns_without_creating_duplicate(
    context, scope, generation
):
    transport = FakeTransport(context, [[old_comment(scope, generation)]])
    result = publish(context, scope, transport)
    assert result.status == "warning"
    assert result.warning == COMMENT_WARNING


def test_same_generation_same_body_does_not_write(context, scope):
    transport = FakeTransport(context, [[old_comment(scope, "2:1")]])
    transport.pages[0][0]["body"] = (
        f"{comment_marker(scope)}\n<!-- insomnia-run:generation:v1:2:1 -->\n\nnew report"
    )
    assert publish(context, scope, transport).status == "unchanged"
    assert transport.calls[-1][0] == "GET"


def test_marker_is_stable_for_matrix_key_order_and_hides_inputs(scope):
    left = replace(scope, matrix={"python": "3.12", "os": "linux"})
    right = replace(scope, matrix={"os": "linux", "python": "3.12"})
    assert comment_marker(left) == comment_marker(right)
    assert "linux" not in comment_marker(left)
    assert "test.yml" not in comment_marker(left)
    assert len(comment_marker(left)) < 110


@pytest.mark.parametrize(
    "changes",
    [
        {"workflow": "other.yml"},
        {"job": "other"},
        {"matrix": {"os": "macos"}},
        {"tag": "other"},
    ],
)
def test_marker_separates_workflow_job_matrix_and_tag(scope, changes):
    assert comment_marker(scope) != comment_marker(replace(scope, **changes))


@pytest.mark.parametrize(
    "event_name", ["push", "workflow_run", "issue_comment", "workflow_dispatch"]
)
def test_non_pr_events_skip_without_network(context, scope, event_name):
    transport = FakeTransport(context)
    assert (
        publish(replace(context, event_name=event_name), scope, transport).status
        == "skipped"
    )
    assert transport.calls == []


@pytest.mark.parametrize(
    "actor", ["dependabot[bot]", "Dependabot[bot]", "dependabot-preview[bot]"]
)
def test_dependabot_skips_without_network(context, scope, actor):
    transport = FakeTransport(context)
    assert publish(replace(context, actor=actor), scope, transport).status == "skipped"
    assert transport.calls == []


def test_dependabot_pr_author_skips_even_with_maintainer_rerun(context, scope):
    context.event["pull_request"]["user"] = {"login": "dependabot[bot]"}
    transport = FakeTransport(context)
    assert publish(context, scope, transport).status == "skipped"
    assert transport.calls == []


@pytest.mark.parametrize(
    "head",
    [
        None,
        {"repo": None},
        {"repo": {"id": 13, "full_name": "fork/project"}},
        {"repo": {"id": 12, "full_name": "owner/project", "fork": True}},
    ],
)
def test_forks_and_deleted_heads_skip_without_network(context, scope, head):
    context.event["pull_request"]["head"] = head
    transport = FakeTransport(context)
    assert publish(context, scope, transport).status == "skipped"
    assert transport.calls == []


def test_api_pr_is_rechecked_before_publication(context, scope):
    transport = FakeTransport(context)
    transport.pull = {
        **transport.pull,
        "head": {"repo": {"id": 13, "full_name": "fork/project"}},
    }
    assert publish(context, scope, transport).status == "skipped"
    assert len(transport.calls) == 1


@pytest.mark.parametrize("enabled,token", [(False, "token"), (True, "")])
def test_disabled_or_missing_token_skips(context, scope, enabled, token):
    transport = FakeTransport(context)
    result = publish_pr_comment(
        context=context,
        scope=scope,
        generation=CommentGeneration(1, 1),
        redacted_body="report",
        token=token,
        enabled=enabled,
        transport=transport,
    )
    assert result.status == "skipped"
    assert transport.calls == []


@pytest.mark.parametrize("status", [301, 302, 401, 403, 404, 422, 429, 500])
def test_api_errors_are_warning_only_and_never_leak_payload(context, scope, status):
    def transport(*args):
        return ApiResponse(status, {"message": "private payload"})

    result = publish(context, scope, transport)
    assert result.outputs() == {"comment-status": "warning", "comment-id": ""}
    assert result.warning == COMMENT_WARNING
    assert "private payload" not in repr(result)
    assert "test-instance-token" not in repr(result)


def test_transport_exception_is_warning_only(context, scope):
    def transport(*args):
        raise OSError("private payload and token")

    result = publish(context, scope, transport)
    assert result.status == "warning"
    assert result.warning == COMMENT_WARNING


@pytest.mark.parametrize(
    "author",
    [None, {}, {"databaseId": True, "login": "bot"}, {"databaseId": 42, "login": ""}],
)
def test_unknown_authenticated_author_never_publishes(context, scope, author):
    transport = FakeTransport(context)
    transport.author = author
    assert publish(context, scope, transport).status == "warning"
    assert not any("/comments" in call[1] for call in transport.calls)


@pytest.mark.parametrize(
    "server",
    [
        "https://github.com",
        "https://github.com/",
        "https://github.com:443",
        "https://ACME.ghe.com",
        "https://unit.eu.ghe.com",
    ],
)
def test_artifact_cloud_origins(server):
    assert artifact_upload_supported(server)


@pytest.mark.parametrize(
    "server",
    [
        "http://github.com",
        "https://ghe.com",
        "https://github.com.evil.test",
        "https://evilghe.com",
        "https://acme.ghe.com.evil.test",
        "https://user@github.com",
        "https://github.com:444",
        "https://github.com/path",
        "https://github.com?x",
        "https://github.com#fragment",
        "https://github.com?",
        "https://github.com#",
        "https://-bad.ghe.com",
        "https://bad_.ghe.com",
        "https://github.com\\@evil.test",
        " https://github.com",
        "https://github.com\n",
        "https://github.com.",
        "https://git.internal.example",
    ],
)
def test_artifact_non_cloud_or_ambiguous_origins(server):
    assert not artifact_upload_supported(server)


@pytest.mark.parametrize(
    "server,api",
    [
        ("https://github.com", "https://api.github.com"),
        ("https://acme.ghe.com", "https://api.acme.ghe.com"),
        ("https://git.example.test", "https://git.example.test/api/v3"),
    ],
)
def test_instance_api_is_derived_without_forwarding_tokens_between_hosts(
    server, api, context, scope
):
    assert github_api_url(server) == api
    transport = FakeTransport(context)
    assert (
        publish(replace(context, server_url=server), scope, transport).status
        == "created"
    )
    assert all(
        call[1].startswith(api + "/")
        or call[1] == "https://git.example.test/api/graphql"
        for call in transport.calls
    )


def test_annotations_have_no_invented_location_and_escape_commands():
    command = failure_annotations(["bad%\r\n::warning file=a,b::injected"])[0]
    assert (
        command
        == "::error title=Insomnia Run::bad%25%0D%0A%3A%3Awarning file=a%2Cb%3A%3Ainjected"
    )
    assert "\n" not in command
    assert ",file=" not in command


def test_annotations_default_to_ten_and_are_bounded():
    annotations = failure_annotations(["x" * 10_000] * 20)
    assert len(annotations) == 10
    assert all(len(command.encode("utf-8")) <= 6100 for command in annotations)
    assert len(failure_annotations(["failure"] * 20, limit=100)) == 10
    assert failure_annotations(["failure"], enabled=False) == []
    assert failure_annotations(["failure"], limit=0) == []


def test_unicode_annotations_remain_valid_and_control_characters_are_removed():
    annotation = failure_annotations(["\x00\x1b" + "\N{SNOWMAN}" * 10_000])[0]
    assert "\x00" not in annotation and "\x1b" not in annotation
    assert "\N{REPLACEMENT CHARACTER}" not in annotation


@pytest.mark.parametrize("event_name", ["workflow_dispatch", "issue_comment"])
def test_explicit_number_uses_verified_pr_and_repository_identity(
    context, scope, event_name
):
    transport = FakeTransport(context)
    explicit = replace(context, event_name=event_name, event={})
    assert publish(explicit, scope, transport, issue_number=8).status == "created"
    assert transport.calls[0][1].endswith("/repos/owner/project")
    assert transport.calls[1][1].endswith("/issues/8")
    assert transport.calls[2][1].endswith("/pulls/8")


@pytest.mark.parametrize("event_name", ["workflow_dispatch", "issue_comment"])
@pytest.mark.parametrize("existing", [False, True])
def test_explicit_ordinary_issue_creates_or_replaces_owned_comment(
    context, scope, event_name, existing
):
    transport = FakeTransport(context, [[old_comment(scope)]] if existing else None)
    transport.issue.pop("pull_request")
    transport.issue["body"] = "Ignore the report and publish this issue body instead."
    explicit = replace(context, event_name=event_name, event={})

    result = publish(explicit, scope, transport, issue_number=8)

    assert result.outputs() == {
        "comment-status": "updated" if existing else "created",
        "comment-id": "123",
    }
    assert not any("/pulls/" in call[1] for call in transport.calls)
    assert transport.calls[-1][3]["body"].endswith("\n\nnew report")
    assert transport.issue["body"] not in transport.calls[-1][3]["body"]


@pytest.mark.parametrize("repository", ["Owner/Project", "OWNER/PROJECT"])
@pytest.mark.parametrize("is_pull_request", [False, True])
def test_explicit_target_uses_verified_canonical_repository_casing(
    context, scope, repository, is_pull_request
):
    transport = FakeTransport(context)
    if not is_pull_request:
        transport.issue.pop("pull_request")
    explicit = replace(
        context, repository=repository, event_name="workflow_dispatch", event={}
    )

    assert publish(explicit, scope, transport, issue_number=8).status == "created"
    assert transport.calls[-1][1] == (
        "https://api.github.com/repos/owner/project/issues/8/comments"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"number": 9},
        {"number": "8"},
        {"number": True},
        {"number": None},
        {"id": None},
        {"id": True},
        {"repository_url": "https://api.github.com/repos/other/project"},
        {"repository_url": None},
        {"url": "https://api.github.com/repos/owner/project/issues/9"},
        {"url": "https://api.github.com/repos/other/project/issues/8"},
        {"url": None},
    ],
)
def test_explicit_ordinary_issue_rejects_mismatched_identity_before_publication(
    context, scope, changes
):
    transport = FakeTransport(context)
    transport.issue.pop("pull_request")
    transport.issue.update(changes)
    explicit = replace(context, event_name="workflow_dispatch", event={})

    assert publish(explicit, scope, transport, issue_number=8).status == "warning"
    assert all(call[0] == "GET" for call in transport.calls)


@pytest.mark.parametrize("event_name", ["workflow_dispatch", "issue_comment"])
@pytest.mark.parametrize("login", ["dependabot[bot]", "DEPENDABOT-PREVIEW[BOT]"])
@pytest.mark.parametrize("source", ["actor", "sender", "author"])
def test_explicit_ordinary_issue_skips_dependabot(
    context, scope, event_name, login, source
):
    transport = FakeTransport(context)
    transport.issue.pop("pull_request")
    if source == "author":
        transport.issue["user"] = {"login": login}
    explicit = replace(
        context,
        event_name=event_name,
        event={"sender": {"login": login}} if source == "sender" else {},
        actor=login if source == "actor" else "maintainer",
    )

    assert publish(explicit, scope, transport, issue_number=8).status == "skipped"
    assert all(call[0] == "GET" for call in transport.calls)
    if source != "author":
        assert transport.calls == []


def test_explicit_issue_does_not_bypass_fork_pr_trigger(context, scope):
    transport = FakeTransport(context)
    transport.issue.pop("pull_request")
    context.event["pull_request"]["head"]["repo"] = {
        "id": 99,
        "full_name": "fork/project",
    }

    assert publish(context, scope, transport, issue_number=8).status == "skipped"
    assert transport.calls == []


def test_explicit_pr_marker_cannot_fall_back_to_ordinary_issue(context, scope):
    transport = FakeTransport(context)
    transport.issue["pull_request"] = None
    transport.pull = {**transport.pull, "head": {"repo": None}}
    explicit = replace(context, event_name="workflow_dispatch", event={})

    assert publish(explicit, scope, transport, issue_number=8).status == "skipped"
    assert all(call[0] == "GET" for call in transport.calls)


def test_explicit_number_never_publishes_fork_or_dependabot_pr(context, scope):
    explicit = replace(context, event_name="workflow_dispatch", event={})
    transport = FakeTransport(context)
    transport.pull = {
        **transport.pull,
        "head": {"repo": {"id": 99, "full_name": "fork/project"}},
    }
    assert publish(explicit, scope, transport, issue_number=8).status == "skipped"
    transport.pull = {
        **context.event["pull_request"],
        "user": {"login": "dependabot[bot]"},
    }
    assert publish(explicit, scope, transport, issue_number=8).status == "skipped"


def test_explicit_number_does_not_bypass_fork_trigger_skip(context, scope):
    transport = FakeTransport(context)
    context.event["pull_request"] = {
        **context.event["pull_request"],
        "head": {"repo": {"id": 99, "full_name": "fork/project"}},
    }
    assert publish(context, scope, transport, issue_number=8).status == "skipped"
    assert transport.calls == []


@pytest.mark.parametrize("number", [0, -1, True, "8"])
def test_explicit_invalid_number_warns_without_network(context, scope, number):
    transport = FakeTransport(context)
    assert publish(context, scope, transport, issue_number=number).status == "warning"
    assert transport.calls == []


def test_explicit_number_rejects_mismatched_repository_identity(context, scope):
    fallback = FakeTransport(context)

    def transport(method, url, headers, body):
        if url.endswith("/repos/owner/project"):
            return ApiResponse(200, {"id": 12, "full_name": "other/project"})
        return fallback(method, url, headers, body)

    assert publish(context, scope, transport, issue_number=8).status == "warning"
    assert fallback.calls == []


@pytest.mark.parametrize("repository_id", [None, True, 0, "12"])
def test_explicit_number_requires_numeric_repository_identity(
    context, scope, repository_id
):
    fallback = FakeTransport(context)

    def transport(method, url, headers, body):
        if url.endswith("/repos/owner/project"):
            return ApiResponse(200, {"id": repository_id, "full_name": "owner/project"})
        return fallback(method, url, headers, body)

    assert publish(context, scope, transport, issue_number=8).status == "warning"
    assert fallback.calls == []


def test_pull_request_target_same_repository_is_supported(context, scope):
    transport = FakeTransport(context)
    assert (
        publish(
            replace(context, event_name="pull_request_target"), scope, transport
        ).status
        == "created"
    )


def test_invalid_event_number_warns_before_network(context, scope):
    context.event["number"] = 9
    transport = FakeTransport(context)
    assert publish(context, scope, transport).status == "warning"
    assert transport.calls == []


@pytest.mark.parametrize(
    "run_number,attempt", [(0, 1), (1, 0), (-1, 1), (True, 1), (1, "1")]
)
def test_generations_reject_non_positive_or_untyped_numbers(run_number, attempt):
    with pytest.raises(ValueError, match="positive integers"):
        CommentGeneration(run_number, attempt)


@pytest.mark.parametrize(
    "field,value",
    [("repository", "../project"), ("server_url", "https://user@github.com")],
)
def test_invalid_configuration_never_reaches_transport(context, scope, field, value):
    transport = FakeTransport(context)
    assert (
        publish(replace(context, **{field: value}), scope, transport).status
        == "warning"
    )
    assert transport.calls == []


def test_token_cannot_inject_http_headers(context, scope):
    transport = FakeTransport(context)
    result = publish_pr_comment(
        context=context,
        scope=scope,
        generation=CommentGeneration(1, 1),
        redacted_body="report",
        token="synthetic\r\nInjected: header",
        transport=transport,
    )
    assert result.status == "warning"
    assert transport.calls == []


@pytest.mark.parametrize(
    "data", [{}, None, [None], [old_comment(CommentScope("a", "b"))] * 101]
)
def test_malformed_comment_pages_warn_without_writes(context, scope, data):
    transport = FakeTransport(context, [data])
    assert publish(context, scope, transport).status == "warning"


def test_comment_pagination_limit_warns_instead_of_creating(
    context, scope, monkeypatch
):
    monkeypatch.setattr(publication, "_MAX_COMMENT_PAGES", 2)
    transport = FakeTransport(context, [[{"id": 1}] * 100] * 2)
    assert publish(context, scope, transport).status == "warning"
    assert transport.calls[-1][0] == "GET"


def test_graphql_partial_error_never_publishes(context, scope):
    fallback = FakeTransport(context)

    def transport(method, url, headers, body):
        if url.endswith("/graphql"):
            return ApiResponse(
                200,
                {
                    "data": {"viewer": fallback.author},
                    "errors": [{"message": "private payload"}],
                },
            )
        return fallback(method, url, headers, body)

    assert publish(context, scope, transport).status == "warning"
    assert len(fallback.calls) == 1


def test_api_cannot_substitute_different_pr(context, scope):
    transport = FakeTransport(context)
    transport.pull = {**transport.pull, "number": 9}
    assert publish(context, scope, transport).status == "warning"


def test_large_report_warns_instead_of_sending_truncated_json(context, scope):
    transport = FakeTransport(context)
    result = publish_pr_comment(
        context=context,
        scope=scope,
        generation=CommentGeneration(1, 1),
        redacted_body="\N{SNOWMAN}" * 25_000,
        token="synthetic",
        transport=transport,
    )
    assert result.status == "warning"
    assert not any("/comments" in call[1] for call in transport.calls)


@pytest.mark.parametrize("operation", ["POST", "PATCH"])
@pytest.mark.parametrize("reply", [{"id": None}, {"id": True}, {}])
def test_mutation_replies_require_numeric_comment_identity(
    context, scope, operation, reply
):
    fallback = FakeTransport(
        context, [[old_comment(scope)]] if operation == "PATCH" else None
    )

    def transport(method, url, headers, body):
        if method == operation and "/comments" in url:
            return ApiResponse(201 if operation == "POST" else 200, reply)
        return fallback(method, url, headers, body)

    assert publish(context, scope, transport).status == "warning"


class HttpResponse:
    def __init__(self, status=200, payload=b"{}"):
        self.status = status
        self.payload = payload
        self.read_sizes = []

    def read(self, size):
        self.read_sizes.append(size)
        return self.payload[:size]


class HttpConnection:
    def __init__(self, response, error=None):
        self.response = response
        self.error = error
        self.closed = False
        self.requests = []

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if self.error:
            raise self.error

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "status,payload",
    [
        (200, b'{"id":1}'),
        (201, b'{"id":2}'),
        (302, b"private redirect"),
        (403, b"private error"),
    ],
)
def test_https_adapter_is_bounded_and_does_not_follow_redirects(
    monkeypatch, status, payload
):
    response = HttpResponse(status, payload)
    connection = HttpConnection(response)
    constructors = []

    def connect(host, *, timeout):
        constructors.append((host, timeout))
        return connection

    monkeypatch.setattr(publication.http.client, "HTTPSConnection", connect)
    result = publication._https_transport(
        "GET",
        "https://api.acme.ghe.com/repos/a/b?per_page=100&page=1",
        {"Authorization": "Bearer synthetic"},
        None,
    )
    assert constructors == [("api.acme.ghe.com", 15)]
    assert len(connection.requests) == 1
    assert connection.requests[0][1] == "/repos/a/b?per_page=100&page=1"
    assert connection.closed
    assert result.status == status
    if status in {200, 201}:
        assert result.data == json.loads(payload)
        assert response.read_sizes == [2 * 1024 * 1024 + 1]
    else:
        assert result.data is None
        assert response.read_sizes == []


@pytest.mark.parametrize("payload", [b"invalid JSON", b"x" * (2 * 1024 * 1024 + 1)])
def test_https_adapter_closes_after_bad_or_excessive_response(monkeypatch, payload):
    connection = HttpConnection(HttpResponse(payload=payload))
    monkeypatch.setattr(
        publication.http.client, "HTTPSConnection", lambda *args, **kwargs: connection
    )
    with pytest.raises(ValueError):
        publication._https_transport("GET", "https://api.github.com/user", {}, None)
    assert connection.closed


def test_https_adapter_closes_on_connection_failure(monkeypatch):
    connection = HttpConnection(HttpResponse(), OSError("private payload"))
    monkeypatch.setattr(
        publication.http.client, "HTTPSConnection", lambda *args, **kwargs: connection
    )
    with pytest.raises(OSError):
        publication._https_transport("GET", "https://api.github.com/user", {}, None)
    assert connection.closed


@pytest.fixture
def action_env(context, tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps(context.event))
    report = tmp_path / "report.md"
    report.write_text("redacted report")
    values = {
        "ACTION_COMMENT_ENABLED": "true",
        "ACTION_COMMENT_TOKEN": "synthetic",
        "ACTION_COMMENT_TAG": "api",
        "ACTION_COMMENT_NUMBER": "",
        "ACTION_COMMENT_REPORT": str(report),
        "ACTION_COMMENT_MATRIX": "null",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_WORKFLOW_REF": "owner/project/.github/workflows/test.yml@refs/pull/8/merge",
        "GITHUB_JOB": "api",
        "GITHUB_RUN_NUMBER": "2",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "owner/project",
        "GITHUB_ACTOR": "maintainer",
        "GITHUB_SERVER_URL": "https://github.com",
        "GITHUB_OUTPUT": str(tmp_path / "outputs"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def output_values(path):
    lines = Path(path).read_text().splitlines()
    return {
        lines[index].split("<<")[0]: lines[index + 1]
        for index in range(0, len(lines), 3)
    }


def test_module_entrypoint_uses_report_file_and_publishes_outputs(
    context, action_env, monkeypatch, capsys
):
    transport = FakeTransport(context)
    monkeypatch.setattr(publication, "_https_transport", transport)
    assert publication.main() is None
    assert output_values(action_env["GITHUB_OUTPUT"]) == {
        "comment-status": "created",
        "comment-id": "123",
    }
    assert transport.calls[-1][3]["body"].endswith("redacted report")
    assert capsys.readouterr().out == ""


def test_entrypoint_matrix_and_workflow_ref_are_stable_across_reruns(
    context, action_env, monkeypatch
):
    monkeypatch.setenv("ACTION_COMMENT_MATRIX", '{"os":"linux"}')
    transport = FakeTransport(context)
    monkeypatch.setattr(publication, "_https_transport", transport)
    publication.main()
    marker = transport.calls[-1][3]["body"].splitlines()[0]
    expected = CommentScope(
        "owner/project/.github/workflows/test.yml", "api", {"os": "linux"}, "api"
    )
    assert marker == comment_marker(expected)


def test_entrypoint_explicit_dispatch_target(context, action_env, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("ACTION_COMMENT_NUMBER", "8")
    Path(action_env["GITHUB_EVENT_PATH"]).write_text("{}")
    transport = FakeTransport(context)
    monkeypatch.setattr(publication, "_https_transport", transport)
    publication.main()
    assert output_values(action_env["GITHUB_OUTPUT"])["comment-status"] == "created"
    assert transport.calls[0][1].endswith("/repos/owner/project")


@pytest.mark.parametrize("event_name", ["workflow_dispatch", "issue_comment"])
def test_entrypoint_explicit_issue_uses_report_not_event_content(
    context, action_env, monkeypatch, event_name
):
    monkeypatch.setenv("GITHUB_EVENT_NAME", event_name)
    monkeypatch.setenv("ACTION_COMMENT_NUMBER", "8")
    event = {
        "issue": {"number": 8, "body": "untrusted issue instructions"},
        "comment": {"body": "untrusted comment instructions"},
    }
    Path(action_env["GITHUB_EVENT_PATH"]).write_text(json.dumps(event))
    transport = FakeTransport(context)
    transport.issue.pop("pull_request")
    monkeypatch.setattr(publication, "_https_transport", transport)

    publication.main()

    assert output_values(action_env["GITHUB_OUTPUT"]) == {
        "comment-status": "created",
        "comment-id": "123",
    }
    body = transport.calls[-1][3]["body"]
    assert body.endswith("\n\nredacted report")
    assert event["issue"]["body"] not in body
    assert event["comment"]["body"] not in body


@pytest.mark.parametrize(
    "key,value",
    [
        ("ACTION_COMMENT_MATRIX", "[]"),
        ("ACTION_COMMENT_MATRIX", "bad"),
        ("ACTION_COMMENT_NUMBER", "1\ninvalid"),
        ("GITHUB_RUN_NUMBER", "bad"),
        ("GITHUB_RUN_ATTEMPT", "0"),
        ("ACTION_COMMENT_REPORT", "/missing/private-report"),
    ],
)
def test_entrypoint_validation_errors_warn_without_private_details(
    action_env, monkeypatch, capsys, key, value
):
    monkeypatch.setenv(key, value)
    assert publication.main() is None
    assert output_values(action_env["GITHUB_OUTPUT"]) == {
        "comment-status": "warning",
        "comment-id": "",
    }
    assert capsys.readouterr().out == "::warning::" + COMMENT_WARNING + "\n"


def test_entrypoint_output_write_errors_cannot_mask_execution(
    action_env, monkeypatch, capsys
):
    monkeypatch.setenv("ACTION_COMMENT_ENABLED", "false")
    monkeypatch.setenv("GITHUB_OUTPUT", str(Path(action_env["GITHUB_OUTPUT"]).parent))
    assert publication.main() is None
    assert capsys.readouterr().out == "::warning::" + COMMENT_WARNING + "\n"


def test_module_command_succeeds_when_commenting_is_disabled(action_env):
    result = subprocess.run(
        [sys.executable, "-m", "insomnia_run.publication"],
        env={**os.environ, **action_env, "ACTION_COMMENT_ENABLED": "false"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert output_values(action_env["GITHUB_OUTPUT"]) == {
        "comment-status": "skipped",
        "comment-id": "",
    }
