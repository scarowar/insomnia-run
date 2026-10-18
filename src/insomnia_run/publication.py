"""Optional GitHub publication; callers supply already-redacted report content."""

import hashlib
import http.client
import json
import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any, Literal, Protocol, TypeGuard
from urllib.parse import urlsplit

from .privacy import escape_workflow_command


COMMENT_WARNING = (
    "Insomnia Run could not publish the report comment; see the workflow report."
)
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_COMMENT_BYTES = 65_000
_MAX_COMMENT_PAGES = 100
_GHES_API_PATH = "/api/v3"
_INVALID_PR_NUMBER = "Invalid pull request number."
_GENERATION = re.compile(
    r"<!-- insomnia-run:generation:v1:([1-9]\d{0,19}):([1-9]\d{0,19}) -->",
    re.ASCII,
)
_DEPENDABOT = {"dependabot[bot]", "dependabot-preview[bot]"}


@dataclass(frozen=True)
class CommentScope:
    """Stable workflow path, job ID, matrix values, and caller-selected tag."""

    workflow: str
    job: str
    matrix: Mapping[str, Any] = field(default_factory=dict)
    tag: str = "default"


@dataclass(frozen=True, order=True)
class CommentGeneration:
    """Workflow run_number and run_attempt, not a commit or a wall-clock time."""

    run_number: int
    run_attempt: int

    def __post_init__(self) -> None:
        if not (_positive_int(self.run_number) and _positive_int(self.run_attempt)):
            raise ValueError("Comment generations must be positive integers.")


@dataclass(frozen=True)
class CommentContext:
    """Repository, event payload, and actor from the trusted runner context."""

    repository: str
    event_name: str
    event: Mapping[str, Any]
    actor: str
    server_url: str = "https://github.com"


@dataclass(frozen=True)
class CommentPublication:
    status: Literal["created", "updated", "unchanged", "skipped", "stale", "warning"]
    comment_id: str = ""
    warning: str = ""

    def outputs(self) -> dict[str, str]:
        return {"comment-status": self.status, "comment-id": self.comment_id}


@dataclass(frozen=True)
class ApiResponse:
    status: int
    data: object


class Transport(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        body: bytes | None,
    ) -> ApiResponse: ...


def _origin(server_url: str) -> tuple[str, str]:
    if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in server_url):
        raise ValueError("Invalid GitHub server origin.")
    parsed = urlsplit(server_url)
    host = parsed.hostname or ""
    labels = host.split(".")
    valid_host = len(host) <= 253 and all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in labels
    )
    if (
        parsed.scheme != "https"
        or not valid_host
        or parsed.netloc.lower() not in {host, host + ":443"}
        or parsed.path not in {"", "/"}
        or "?" in server_url
        or "#" in server_url
    ):
        raise ValueError("Invalid GitHub server origin.")
    return "https://" + host, host


def artifact_upload_supported(server_url: str) -> bool:
    """Cloud artifact actions support github.com and data-resident GHEC, not GHES."""
    try:
        _, host = _origin(server_url)
    except ValueError:
        return False
    return host == "github.com" or host.endswith(".ghe.com")


def github_api_url(server_url: str) -> str:
    """Derive the instance API; never route an enterprise token to github.com."""
    origin, host = _origin(server_url)
    if host == "github.com":
        return "https://api.github.com"
    if host.endswith(".ghe.com"):
        return "https://api." + host
    return origin + _GHES_API_PATH


def comment_marker(scope: CommentScope) -> str:
    identity = json.dumps(
        [scope.workflow, scope.job, dict(scope.matrix), scope.tag],
        sort_keys=True,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"<!-- insomnia-run:comment:v1:{digest} -->"


def _https_transport(
    method: str, url: str, headers: Mapping[str, str], body: bytes | None
) -> ApiResponse:
    parsed = urlsplit(url)
    connection = http.client.HTTPSConnection(parsed.netloc, timeout=15)
    path = parsed.path + ("?" + parsed.query if parsed.query else "")
    try:
        connection.request(method, path, body=body, headers=dict(headers))
        response = connection.getresponse()
        if response.status not in {200, 201}:
            return ApiResponse(response.status, None)
        data = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(data) > _MAX_RESPONSE_BYTES:
            raise ValueError("GitHub API response exceeded the size limit.")
        return ApiResponse(response.status, json.loads(data))
    finally:
        connection.close()


def _positive_int(value: object) -> TypeGuard[int]:
    return type(value) is int and value > 0


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid GitHub API object.")
    return value


def _login(value: object) -> str:
    return str(value.get("login", "")).lower() if isinstance(value, dict) else ""


def _trusted_pr(pull: object, repository: str, repository_id: object) -> bool:
    if not isinstance(pull, dict) or _login(pull.get("user")) in _DEPENDABOT:
        return False
    if not _positive_int(repository_id):
        return False
    # A workflow repository can itself be a fork; require identity, not ancestry.
    for side in ("head", "base"):
        branch = pull.get(side)
        repo = branch.get("repo") if isinstance(branch, dict) else None
        if (
            not isinstance(repo, dict)
            or not _positive_int(repo.get("id"))
            or repo["id"] != repository_id
            or str(repo.get("full_name", "")).lower() != repository.lower()
        ):
            return False
    return True


def _owned_comment(
    entry: object, author_id: int, author_login: str, marker: str
) -> tuple[CommentGeneration, int, str] | None:
    comment = _object(entry)
    user, text = comment.get("user"), comment.get("body")
    if not isinstance(user, dict) or not _positive_int(user.get("id")):
        return None
    if user["id"] != author_id or _login(user) != author_login.lower():
        return None
    if not isinstance(text, str) or not text.startswith(marker + "\n"):
        return None
    lines = text.split("\n", 3)
    match = _GENERATION.fullmatch(lines[1])
    comment_id = comment.get("id")
    if not match or not _positive_int(comment_id) or len(lines) != 4 or lines[2] != "":
        raise ValueError("Invalid owned comment metadata.")
    return CommentGeneration(int(match[1]), int(match[2])), comment_id, text


def _comment_pages(
    request: Callable[[str, str, object], object], comments_url: str
) -> Iterable[object]:
    for page in range(1, _MAX_COMMENT_PAGES + 1):
        comments = request("GET", f"{comments_url}?per_page=100&page={page}", None)
        if not isinstance(comments, list) or len(comments) > 100:
            raise ValueError("Invalid comment page.")
        yield from comments
        if len(comments) < 100:
            return
    raise ValueError("Comment pagination exceeded the limit.")


def publish_pr_comment(
    *,
    context: CommentContext,
    scope: CommentScope,
    generation: CommentGeneration,
    redacted_body: str,
    token: str,
    enabled: bool = True,
    issue_number: int | None = None,
    transport: Transport | None = None,
) -> CommentPublication:
    """Replace this job's comment; failures warn and do not decide run success.

    Callers must serialize all writers sharing a marker. GitHub has no atomic
    comment upsert: the generation guard prevents stale writes only under that
    serialization. No retry follows an ambiguous create response.
    """
    if not enabled or not token:
        return CommentPublication("skipped")
    if issue_number is None and context.event_name not in {
        "pull_request",
        "pull_request_target",
    }:
        return CommentPublication("skipped")
    try:
        return _publish(
            context,
            scope,
            generation,
            redacted_body,
            token,
            transport or _https_transport,
            issue_number,
        )
    except Exception:
        # Publication is optional; exception text and API bodies may hold secrets.
        return CommentPublication("warning", warning=COMMENT_WARNING)


def _publish(
    context: CommentContext,
    scope: CommentScope,
    generation: CommentGeneration,
    redacted_body: str,
    token: str,
    transport: Transport,
    issue_number: int | None,
) -> CommentPublication:
    event = context.event
    if (
        context.actor.lower() in _DEPENDABOT
        or _login(event.get("sender")) in _DEPENDABOT
    ):
        return CommentPublication("skipped")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", context.repository
    ):
        raise ValueError("Invalid repository.")
    if any(ord(c) < 32 or ord(c) == 127 for c in token):
        raise ValueError("Invalid publication token.")
    api = github_api_url(context.server_url)
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "insomnia-run",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    def request(method: str, url: str, payload: object = None) -> object:
        data = (
            json.dumps(payload, ensure_ascii=True).encode("utf-8")
            if payload is not None
            else None
        )
        response = transport(method, url, headers, data)
        if response.status != (201 if method == "POST" and url != graphql else 200):
            raise ValueError("GitHub API request failed.")
        return response.data

    graphql = (
        api.removesuffix(_GHES_API_PATH) + "/api/graphql"
        if api.endswith(_GHES_API_PATH)
        else api + "/graphql"
    )
    target = _verified_target(context, issue_number, request, api)
    if target is None:
        return CommentPublication("skipped")
    number, repo_url = target
    author = _authenticated_author(request, graphql)
    return _upsert_comment(
        request, repo_url, number, author, scope, generation, redacted_body
    )


def _verified_target(
    context: CommentContext,
    issue_number: int | None,
    request: Callable[[str, str, object], object],
    api: str,
) -> tuple[int, str] | None:
    number, repository_id, repo_url = _target(context, issue_number, request, api)
    if number is None:
        return None
    is_pull_request = True
    if issue_number is not None:
        issue_url = f"{repo_url}/issues/{number}"
        issue = _object(request("GET", issue_url, None))
        if (
            not _positive_int(issue.get("id"))
            or not _positive_int(issue.get("number"))
            or issue["number"] != number
            or issue.get("repository_url") != repo_url
            or issue.get("url") != issue_url
        ):
            raise ValueError("Mismatched issue identity.")
        if _login(issue.get("user")) in _DEPENDABOT:
            return None
        is_pull_request = "pull_request" in issue
    if is_pull_request:
        live_pull = request("GET", f"{repo_url}/pulls/{number}", None)
        if not _trusted_pr(live_pull, context.repository, repository_id):
            return None
        if _object(live_pull).get("number") != number:
            raise ValueError("Mismatched pull request number.")
    return number, repo_url


def _authenticated_author(
    request: Callable[[str, str, object], object], graphql: str
) -> tuple[int, str]:
    viewer_response = _object(
        request("POST", graphql, {"query": "query { viewer { databaseId login } }"})
    )
    if viewer_response.get("errors"):
        raise ValueError("GitHub identity query failed.")
    viewer = _object(_object(viewer_response.get("data")).get("viewer"))
    author_id, author_login = viewer.get("databaseId"), viewer.get("login")
    if (
        not _positive_int(author_id)
        or not isinstance(author_login, str)
        or not author_login
    ):
        raise ValueError("Unknown authenticated comment author.")

    return author_id, author_login


def _upsert_comment(
    request: Callable[[str, str, object], object],
    repo_url: str,
    number: int,
    author: tuple[int, str],
    scope: CommentScope,
    generation: CommentGeneration,
    redacted_body: str,
) -> CommentPublication:
    marker = comment_marker(scope)
    body = f"{marker}\n<!-- insomnia-run:generation:v1:{generation.run_number}:{generation.run_attempt} -->\n\n{redacted_body}"
    if len(body.encode("utf-8")) > _MAX_COMMENT_BYTES:
        raise ValueError("Comment exceeded the size limit.")
    comments_url = f"{repo_url}/issues/{number}/comments"
    existing = (
        _owned_comment(entry, *author, marker)
        for entry in _comment_pages(request, comments_url)
    )
    latest = max((entry for entry in existing if entry is not None), default=None)
    if latest is not None:
        previous, comment_id, text = latest
        if previous > generation:
            return CommentPublication("stale", str(comment_id))
        if text == body:
            return CommentPublication("unchanged", str(comment_id))
        response = _object(
            request("PATCH", f"{repo_url}/issues/comments/{comment_id}", {"body": body})
        )
        if not _positive_int(response.get("id")) or response["id"] != comment_id:
            raise ValueError("Mismatched updated comment ID.")
        return CommentPublication("updated", str(comment_id))
    response = _object(request("POST", comments_url, {"body": body}))
    if not _positive_int(response.get("id")):
        raise ValueError("Invalid created comment ID.")
    return CommentPublication("created", str(response["id"]))


def _target(
    context: CommentContext,
    issue_number: int | None,
    request: Callable[[str, str, object], object],
    api: str,
) -> tuple[int | None, object, str]:
    repo_url = f"{api}/repos/{context.repository}"
    repository_id = None
    if context.event_name in {"pull_request", "pull_request_target"}:
        repository_id = _object(context.event.get("repository")).get("id")
        if not _trusted_pr(
            context.event.get("pull_request"), context.repository, repository_id
        ):
            return None, repository_id, repo_url
    if issue_number is not None:
        if not _positive_int(issue_number):
            raise ValueError(_INVALID_PR_NUMBER)
        repository = _object(request("GET", repo_url, None))
        if str(
            repository.get("full_name", "")
        ).lower() != context.repository.lower() or not _positive_int(
            repository.get("id")
        ):
            raise ValueError("Mismatched repository identity.")
        return (
            issue_number,
            repository["id"],
            f"{api}/repos/{repository['full_name']}",
        )
    pull = context.event.get("pull_request")
    number = _object(pull).get("number")
    if (
        not _positive_int(number)
        or type(context.event.get("number")) is not int
        or context.event["number"] != number
    ):
        raise ValueError(_INVALID_PR_NUMBER)
    return number, repository_id, repo_url


def failure_annotations(
    redacted_messages: Iterable[str], *, enabled: bool = True, limit: int = 10
) -> list[str]:
    """Return bounded workflow commands without inventing source locations."""
    if not enabled:
        return []
    commands = []
    for message in islice(redacted_messages, max(0, min(limit, 10))):
        text = message.encode("utf-8")[:2000].decode("utf-8", errors="ignore")
        text = "".join(
            c if (ord(c) >= 32 and ord(c) != 127) or c in "\r\n" else " " for c in text
        )
        commands.append("::error title=Insomnia Run::" + escape_workflow_command(text))
    return commands


def _environment_publication(env: Mapping[str, str]) -> CommentPublication:
    if env.get("ACTION_COMMENT_ENABLED", "").lower() != "true":
        return CommentPublication("skipped")
    event = _object(
        json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    )
    matrix = json.loads(env.get("ACTION_COMMENT_MATRIX") or "null")
    if matrix is not None and not isinstance(matrix, dict):
        raise ValueError("Invalid workflow matrix.")
    workflow = env["GITHUB_WORKFLOW_REF"].split("@", 1)[0]
    issue_number = env.get("ACTION_COMMENT_NUMBER", "").strip()
    if issue_number and not re.fullmatch(r"[1-9]\d*", issue_number, re.ASCII):
        raise ValueError(_INVALID_PR_NUMBER)
    return publish_pr_comment(
        context=CommentContext(
            repository=env["GITHUB_REPOSITORY"],
            event_name=env["GITHUB_EVENT_NAME"],
            event=event,
            actor=env["GITHUB_ACTOR"],
            server_url=env.get("GITHUB_SERVER_URL", "https://github.com"),
        ),
        scope=CommentScope(
            workflow,
            env["GITHUB_JOB"],
            matrix or {},
            env.get("ACTION_COMMENT_TAG", "default"),
        ),
        generation=CommentGeneration(
            int(env["GITHUB_RUN_NUMBER"]), int(env["GITHUB_RUN_ATTEMPT"])
        ),
        redacted_body=Path(env["ACTION_COMMENT_REPORT"]).read_text(encoding="utf-8"),
        token=env.get("ACTION_COMMENT_TOKEN", ""),
        issue_number=int(issue_number) if issue_number else None,
    )


def main() -> None:
    """Action adapter: comment errors never replace the execution exit policy."""
    try:
        result = _environment_publication(os.environ)
    except Exception:
        result = CommentPublication("warning", warning=COMMENT_WARNING)
    try:
        from .action_runtime import write_outputs

        write_outputs(Path(os.environ["GITHUB_OUTPUT"]), result.outputs())
    except Exception:
        result = CommentPublication("warning", warning=COMMENT_WARNING)
    if result.warning:
        print("::warning::" + COMMENT_WARNING)


if __name__ == "__main__":
    main()
