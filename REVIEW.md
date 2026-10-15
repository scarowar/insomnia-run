# v0.2.0 Candidate Review

## Scope

Review the complete candidate against merge base `31f82a6213d9bdd723aca42ec86dff4e928100fb`, starting at `c388ee84cf8ab36da4121d974f4a68c8516ea264`. No merge, tag, release, access grant, or branch-protection bypass is authorized by this review.

The product goal is a reliable, secure, maintainable unofficial GitHub Action for current Inso. The action must reduce avoidable installation API requests, support exact preinstalled tools, verify downloaded and cached binaries, preserve test failures, and produce usable reports. Approved additions are verified archive caching and optional report uploads. ClusterFuzzLite is explicitly deferred. This is a solo-maintainer project; recruiting another maintainer is not a prerequisite for technical work. Existing review rules remain unchanged unless separately approved.

## Review Contract

Each round uses separate reviewer contexts, followed by reproduction, fixes, and another multi-perspective review. Reviewer opinions are inputs, not proof. Record findings as confirmed, fixed, rejected with evidence, optional, or explicitly deferred. Do not manufacture findings or rewrite working code to fill a rubric.

| Perspective | Evidence Required |
| --- | --- |
| Product and specification | Documented inputs, outputs, commands, defaults, supported runners, and migration behavior match the actual user workflow. |
| Correctness and compatibility | Passing, failing, skipped, empty, interrupted, malformed, and repeated executions have intentional exit and report behavior; current real Inso works. |
| Latest upstream conformance | Account for every supported input and wrapper option against the latest stable release's help, official docs, exact-release source, and release notes. Explicitly enumerate unsupported upstream run options and discrepancies instead of claiming unverified 100% conformance. |
| Security and supply chain | Untrusted inputs cannot inject commands or workflow outputs; secrets are not exposed unintentionally; executable downloads fail closed; token and cache trust boundaries are explicit. |
| Reliability and operations | Cold installs, cache hits, corrupt caches, preinstalled tools, retries, timeouts, publication failures, and repeated invocations are exercised at their real boundaries. |
| Simplicity and architecture | KISS, YAGNI, and DRY improve comprehension and ownership without speculative abstractions or deleting useful behavior. |
| Testing and verification | Regression tests fail before fixes, exercise observable behavior, and detect representative mutations; static checks do not substitute for runtime evidence. |
| Documentation and solo maintenance | Examples are runnable in their stated context; limitations and maintainer decisions are factual rather than invented release blockers. |

## Skill Sources

Only applicable Python, CLI, GitHub Actions, security, testing, design, and review guidance is used. Frontend/browser and TypeScript-specific guidance is excluded. Skill guidance is adapted to this repository's scope and takes no authority over project or user instructions.

- Matt Pocock: `mattpocock/skills@49dd158d1076134a641b33efb035946536778336`, engineering code review, TDD, codebase design, and bug diagnosis. Standards and specification findings remain separate.
- Addy Osmani: `addyosmani/agent-skills@aeac41d4d005999432bb7312f7ff06383a91d59d`, five-axis review, security, CI, interfaces, simplification, testing, diagnosis, migration, documentation, observability, performance, and source verification.
- Pstack: `backnotprop/pstack@6f131f137de64fdaf928278c0fd9ecec520ccbee`, boundary discipline, behavior-focused tests, subtraction before addition, direct verification, reader load, experience first, and root-cause fixes.

## Round 1

Status: findings fixed and independently re-reviewed below. Standards, specification, security, and runtime reviewers inspected the baseline candidate in separate contexts. The coordinator reviewed action execution and publication paths and reproduced reported defects.

| ID | Severity | Finding | Disposition and Evidence |
| --- | --- | --- | --- |
| R1-01 | P1 | A newline in a custom JUnit filename injected a second GitHub output and replaced a failed CLI exit with success. | Fixed by one delimiter-safe output writer. `test_custom_junit_path_cannot_overwrite_failure_outputs` failed with exit output `0` before the fix and preserves `1` after it. |
| R1-02 | P2 | A custom JUnit path could publish a previous invocation's report after a CLI error. | Fixed by generating each report privately, then copying a fresh file to the requested destination. `test_custom_junit_path_does_not_publish_a_previous_report` failed before the fix and passes without deleting the previous destination file. |
| R1-03 | P2 | A previous invocation's downloaded Inso overrode a correctly detected preinstalled version. | Independently found by the standards and security reviewers. Both actual verification and execution reproducers failed before the fix; the invocation's selection now controls PATH in both steps. |
| R1-04 | P2 | The CI Gitleaks hook scans staged changes, so a clean checkout scans no committed content. | Fixed with a pinned manual-stage committed-content hook, retaining staged-only local behavior. Actual Gitleaks 8.30.0 regression: one failure before the fix, three passing cases after, with redacted findings and no skips in the security environment. |
| R1-05 | P3 | The opt-in compatibility fixture validated one executable but could run a different `inso` from PATH. | Fixed with a private exact-binary alias. A differently named controlled executable and competing PATH executable reproduced the mismatch before the fix; the regression now passes. |
| R1-06 | P1 | Synthetic execution failures copied arbitrary Inso diagnostics into public result descriptions despite raw-output opt-in being disabled. | Fixed with bounded execution-error results. Public CLI subprocess regressions verify opt-in-only diagnostics across Markdown, JSON, and JUnit, with partial TAP and stdout/stderr errors. |
| R1-07 | P1 | Missing test-suite TAP, truncated plans, and bailouts could produce successful reports. | Fixed with plan completeness, assertion-order, and bailout validation. Repeated collection plans, trailing Mocha plans, intentional empty plans, and assertion-free collections remain supported. See upstream correction U-01. |
| R1-08 | P1 | A target named `--help` was interpreted as an Inso option, returning success without executing tests. | Fixed with a terminal option separator after all options. Behavioral regressions and independent real Inso 13.3.1 inspection confirm option-like targets are identifiers, not flags. |
| R1-09 | P1 | An unexpected CLI error or report-write error could print secret option values from Typer's local variables. | Fixed: disable exception locals and handle report I/O errors with a bounded message. Real CLI subprocess regressions verify both handled and unexpected exceptions. Invalid env-var diagnostics also no longer echo the supplied value. |
| R1-10 | P2 | The execution timeout stopped the launcher but left its Inso descendants running. | Fixed with isolated POSIX process-group cleanup and bounded pipe draining. A real descendant-lock regression verifies termination; detached-pipe and interrupt regressions verify bounded cleanup preserves the original exception. Windows is explicitly unsupported. |
| R1-11 | P2 | Zero/negative iteration counts and invalid timeout bounds could be silently ignored, skip execution, or fail after starting work. | Fixed at both CLI and typed-model boundaries; iteration and execution timeouts must be positive, request timeout and delay nonnegative. Fourteen boundary cases failed before the constraints and pass afterward. Explicit zero request timeout/delay remains supported. |
| R1-12 | P2 | Empty/all-skipped Markdown claimed tests passed and counted assertions as HTTP requests. | Fixed: neutral empty/skipped status and test-result counts. Three new regressions failed before the fix; reporter tests pass. Raw-diagnostic instructions now explain opt-in and secret exposure rather than promising hidden logs in the workflow. |
| R1-13 | P3 | Subprocess decoding depended on the runner locale and could discard reports on invalid bytes. | Fixed with explicit UTF-8 replacement decoding. Real subprocess regressions cover valid Unicode, invalid bytes, and a non-UTF-8 parent locale. |
| R1-14 | P3 | The parser treated descriptions containing `# SKIPPER` as skipped failures. | Fixed with complete SKIP-token matching; regressions preserve these failures and actual skip directives. |
| R1-15 | P2 | The action accepted a successful CLI invocation with missing requested JSON output. | Fixed: validate even empty JSON output. The new empty-output regression failed with exit output `0` before the fix and passes with `1`; genuine CLI nonzero exits are preserved. |
| R1-16 | P2 | Documentation used the wrong legacy Git Sync working directory, implied arbitrary preinstalled versions work offline, and obscured unreleased references and diagnostic privacy. | Fixed with explicit export/root examples, exact-version offline guidance, standalone preview-reference notices, and privacy-aware debugging instructions. Parsed YAML and documentation contract tests pass. |

Mutation check: replacing the safe JUnit output write with the former scalar write, in memory only, makes the exit-code-injection regression fail with `0` instead of `1`. The mutation was detected; tracked source was not altered by the experiment.

Privacy mutation check: enabling Typer exception locals in an isolated subprocess exposes the harmless secret sentinel that the unexpected-exception regression protects. The current default omits it. No real credentials were used.

Runtime mutation checks detected reintroduced diagnostic copying and dict-only environment forwarding. The independent security reviewer also confirmed the PATH-selection regression detects an in-memory reversion. These are targeted mutation checks, not a claim of exhaustive mutation coverage.

## Latest Upstream Audit

Latest stable `core@13.3.1`, published 2026-10-09, was verified through the official release API on 2026-10-15, against binary help/version and source commit `abbf55892e16adafea6eb1d6c12af2fa85d32dc9`. The complete option inventory, deliberate restrictions, unsupported surfaces, and upstream documentation discrepancies are in [the compatibility reference](docs/reference/compatibility.md).

| ID | Severity | Finding | Disposition and Evidence |
| --- | --- | --- | --- |
| U-01 | P1 | The first completeness fix rejected legitimate assertion-free collections because upstream emits no TAP for them. | Caught before commit by the conformance reviewer and existing generated tests. Corrected: require TAP for test suites, but permit truly TAP-free collection success. Incomplete observed TAP and bailouts still fail. The real 13.3.1 assertion-free collection case passes with a neutral empty report. |
| U-02 | P2 | Action metadata and CLI help still advertised the `.insomnia` directory rather than its parent. | Corrected remaining public descriptions; documented export, legacy Git repository, and app-data formats without removing supported upstream formats. |
| U-03 | P2 | Test filters were described as regex even though 13.3.1 uses literal Mocha `fgrep`. | Corrected metadata, CLI help, reference, and examples; documented the upstream discrepancy. Real-binary literal-versus-regex-looking filter cases cover this behavior. |
| U-04 | P2 | Configuration guidance promised arbitrary `.insorc` run defaults and scripts that this release/wrapper does not load or execute. | Replaced with exact discovery, imported-key, precedence, and unsupported-command limits; action inputs remain the explicit run configuration boundary. |
| U-05 | P2 | Collapsing repeated environment overrides into a dictionary lost upstream occurrences and decoded keys. | Fixed with ordered raw occurrences while retaining existing typed dictionary callers. An actual CLI-to-subprocess argv regression failed before the fix; real Inso HTTP header round-trip confirms later-key precedence, retained earlier keys, and URL decoding. |

The audit also checked release assets, units/defaults, repeated options, proxy inheritance, CSV/JSON iteration paths and URLs, and relevant patch changes. It did not add desktop functionality or duplicate Inso's execution/rendering engines. Stricter numeric validation, fixed CI/TAP mode, and unsupported execution-data export flags are explicit rather than disguised as universal conformance.

## Round 2 and Fix Loop

Fresh reviewer contexts separately examined security/reliability, runtime correctness, and standards/product/CLI behavior after Round 1 fixes. Runtime and security reviews found no additional actionable code defects. Their focused checks included actual process boundaries, a PATH mutation, committed-secret redaction, and real Inso identifier handling. Product/specification review found the following documentation defects, which were reproduced and fixed:

| ID | Severity | Finding | Disposition and Evidence |
| --- | --- | --- | --- |
| R2-01 | P2 | Direct secret examples obscured Inso URL decoding, silently altering reserved characters. | Added explicit decoding limits and a first-class percent-encoding example. The exact documented script is executed in a regression with reserved characters and newlines; decoded values round-trip unchanged. The wrapper retains upstream-compatible passthrough. |
| R2-02 | P2 | Multi-environment jobs never checked out the export file. | Added pinned checkout with nonpersistent credentials to each job. The parsed-workflow contract failed before the fix and passes afterward. |
| R2-03 | P3 | The new explicit mask command registered the wrong encoded mask because GitHub decodes workflow-command payloads. | Independently found by both follow-up reviewers. Escaped percent signs in the mask payload only, leaving output values unchanged. The strengthened exact-script regression failed before the correction and now compares runner-decoded masks with encoded outputs. This was a mask-contract bug, not evidence of a guaranteed credential leak; GitHub secret contexts also provide automatic encoding masks. |

Both follow-up reviewers rechecked these fixes and reported no remaining actionable findings in scope. They also inspected the new compatibility matrix and existing-E2E-job wiring; independent runtime review covered the corrected empty behavior and bounded cleanup. Reviews are separate model contexts, not different-model or human approval claims.

## Design Dispositions

- KISS: retain the existing runner/parser/reporter ownership; do not add a generic execution framework or dependency for these narrow boundaries.
- DRY: one workflow-output writer protects every published value. Preserve the existing common option builder; do not introduce shared base models just to remove a few declarations.
- YAGNI: do not expose unrelated upstream commands, security-sensitive execution-data exports, or reporter selection that would break parsed reporting. Their unsupported status is explicit.
- Product quality: prioritize trustworthy failures, exact executable selection, verified installs/caches, privacy defaults, current upstream behavior, and runnable examples. No comparative claim of being the best action is made without comparative evidence.
- Maintenance: targeted behavioral regressions and generated-input properties remain alongside contract checks. Current command-help inventories and real-binary behavior now run in the existing required E2E test-command job, using an isolated frozen test environment and the already verified Inso binary.

## Verification

- Final local Python 3.12 full suite: 300 passed, 15 opt-in compatibility skips, 98.8% source coverage. Python 3.15: 297 passed, 16 skips, 98.78% coverage before the final literal-filter cases were added. Its additional scanner skips are expected because that environment intentionally installs only the test group; the security environment separately runs all three real scanner regressions without skips.
- All 15 real Inso 13.3.1 cases passed across targeted runs: passing/failing collection and test reports, iterations, missing-workspace failure, assertion-free collections, environment override round-trip, all three help inventories, and literal-versus-regex-looking filters. Hosted CI runs the complete suite together from the installed candidate wheel.
- Actual action installation succeeded with `UV_OFFLINE=true` and the prepopulated locked-package/build-backend cache. The installed production wheel then ran through the actual composite-action shell and verified Inso: three passing results and fresh Markdown, JSON, and JUnit files.
- Ruff, mypy, strict documentation build, actionlint, Bandit, dependency audit, Zizmor, and hook checks passed; formatter auto-fixes were rechecked separately. Hosted checks for the committed candidate remain pending.

Residual limits: native macOS execution and remote artifact/comment delivery require hosted evidence; the local environment cannot stand in for those services. Process-group cleanup cannot terminate descendants that deliberately create another session. Default raw-output omission is not a universal secret redactor. ClusterFuzzLite remains owner-deferred. No settings or protection bypasses were changed.

## Exit Criteria

- Every confirmed correctness, security, reliability, or contract defect has a regression-tested fix or an explicit unresolved disposition.
- A later multi-perspective round reviews both fixes and their surrounding behavior; no unresolved release-blocking code defects remain.
- The final candidate passes the Python matrix, security checks, documentation build, and Linux/macOS action E2E checks. Current-Inso compatibility and relevant offline installation checks use the candidate's runtime code.
- Report evidence and remaining limitations honestly. Do not call agent review independent human approval, claim perfect security, or equate a maximal Scorecard score with product quality.
- Keep the version unreleased. Document the owner's final release decision separately from automated technical verification.
