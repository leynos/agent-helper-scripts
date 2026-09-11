"""Shared harness for executing Scrutineer's published Actions procedures.

The `scrutineer` entry in `agents/subagents.yml` publishes its GitHub Actions
workflow as fenced `bash` snippets. These helpers extract those snippets and run
them verbatim against a cmd-mox `gh` double, so the manifest stays the single
authoritative copy of the procedure. Nothing here restates a procedure: a test
that pasted its own copy would keep passing once the manifest drifted, which is
the regression most worth catching.

The double is deliberately strict. It validates the repository, run ID, attempt,
commit SHA, PR number, and the flags each subcommand must carry, and records a
violation for anything that does not match the assignment it was built for. A
lenient double would let a procedure address the wrong run and still look green,
which is the failure mode these tests exist to exclude. `expected_violations`
inverts the check so the validator itself can be shown to bite.

Three details of this boundary are easy to get wrong:

- A cmd-mox shim reads its standard input, so the shell runs with
  `stdin=DEVNULL`. Inheriting pytest's stdin wedges the shim and the shell
  waiting on it.
- cmd-mox rewrites `PATH` and `CMOX_IPC_SOCKET` in `os.environ` when replay
  starts, so the child environment must be built *after* `mox.replay()`.
- `BASH_ENV` makes a non-interactive `bash -c` source a startup file, and such a
  file commonly prepends a directory to `PATH`. That silently shadows the shim
  with the operator's real `gh`, which would turn these tests into live GitHub
  calls. It is cleared, and `assert_gh_is_doubled` then refuses to run anything
  unless `gh` still resolves inside the shim directory.

Only `gh` is doubled. `bash`, `jq`, `date`, and `timeout` are the real programs,
because the procedures' behaviour under them is part of what is being tested.
"""

from __future__ import annotations

import dataclasses as dc
import json
import os
import re
import shutil
import subprocess
import textwrap
import time
import typing as typ
from pathlib import Path

from cmd_mox.ipc import Invocation
from subagent_manifest import load_subagent_entry

if typ.TYPE_CHECKING:
    from collections.abc import Callable, Sequence

BASH = shutil.which("bash")
TIMEOUT = shutil.which("timeout")
JQ = shutil.which("jq")

MISSING_PREREQUISITES = [
    name
    for name, path in (("bash", BASH), ("timeout", TIMEOUT), ("jq", JQ))
    if path is None
]

BASH_FENCE_RE = re.compile(r"```bash\n(?P<body>.*?)```", re.DOTALL)

# Real `gh pr checks` output is `name<TAB>status<TAB>elapsed<TAB>url<TAB>desc`.
# Actions links carry `/actions/runs/<run>/job/<job>`; app checks carry a
# foreign host, and some report no URL at all. Every column below is shaped
# after genuine output from this repository's own pull request.
PR_CHECKS_TSV = (
    "Makefile gates\tpass\t1m11s\t"
    "https://github.com/octo/example/actions/runs/34537499940/job/103072412483\t\n"
    "Kody Code Review\tskipping\t1s\thttps://kodus.io\t\n"
    "Sourcery review\tskipping\t0\thttps://sourcery.ai\t\n"
    "automerge\tskipping\t0\t"
    "https://github.com/octo/example/actions/runs/34537498828/job/103072409707\t\n"
    "CodeRabbit\tpass\t0\t\tReview completed\n"
)
# The same run appears once per job; a second job of run 34537499940 proves the
# deduplication requirement rather than assuming it.
PR_CHECKS_TSV_DUPLICATED = PR_CHECKS_TSV + (
    "Makefile gates (rerun)\tpass\t1m02s\t"
    "https://github.com/octo/example/actions/runs/34537499940/job/103072412999\t\n"
)

ACTIONS_RUN_IDS = ("34537498828", "34537499940")
NON_ACTIONS_CHECKS = ("Kody Code Review", "Sourcery review", "CodeRabbit")


class GhContractViolation(RuntimeError):
    """Raised when the doubled `gh` is addressed with the wrong arguments."""


@dc.dataclass(frozen=True)
class Assignment:
    """The candidate identity a procedure run is expected to address."""

    repo: str = "octo/example"
    pr_number: str = "124"
    run_id: str = "34537499940"
    attempt: str = "2"
    expected_sha: str = "9769ee4b0f51ca8a96531357920cedff54dcc6ee"
    base_ref: str = "main"


def scrutineer_snippets() -> list[str]:
    """Return every fenced bash snippet from Scrutineer's instructions."""
    instructions = typ.cast("str", load_subagent_entry("scrutineer")["instructions"])
    return [
        textwrap.dedent(match.group("body"))
        for match in BASH_FENCE_RE.finditer(instructions)
    ]


def snippet_containing(needle: str) -> str:
    """Return the single published snippet containing ``needle``.

    Selecting by content rather than by position keeps each test bound to the
    procedure it exercises, so reordering the manifest cannot silently swap one
    procedure for another.
    """
    matches = [snippet for snippet in scrutineer_snippets() if needle in snippet]
    if len(matches) != 1:
        message = (
            f"expected exactly one published snippet containing {needle!r}, "
            f"found {len(matches)}"
        )
        raise AssertionError(message)
    return matches[0]


def _flag_value(args: Sequence[str], flag: str) -> str | None:
    """Return the value following ``flag``, or None when it is absent."""
    if flag not in args:
        return None
    index = args.index(flag)
    if index + 1 >= len(args):
        return None
    return args[index + 1]


class GhDouble:
    """An argument-validating stand-in for the `gh` CLI.

    Every invocation is checked against the assignment before any canned output
    is returned, so a procedure that addresses the wrong repository, run,
    attempt, or commit fails loudly instead of quietly passing.
    """

    def __init__(
        self,
        assignment: Assignment,
        *,
        pr_checks: str = PR_CHECKS_TSV,
        run_list: Sequence[dict[str, object]] | None = None,
        candidate: dict[str, object] | None = None,
        latest_attempt: str | None = None,
        watch_exit: int = 0,
        watch_delay: float = 0.0,
        logs_exit: int = 0,
        bundle_dir: Path | None = None,
        watcher_marker: str = "watcher-started.marker",
    ) -> None:
        self.assignment = assignment
        self.pr_checks = pr_checks
        self.run_list = run_list
        self.candidate = candidate
        self.latest_attempt = latest_attempt or assignment.attempt
        self.watch_exit = watch_exit
        self.watch_delay = watch_delay
        self.logs_exit = logs_exit
        self.bundle_dir = bundle_dir
        self.watcher_marker = watcher_marker
        self.violations: list[str] = []
        self.invocations: list[list[str]] = []

    # -- validation -------------------------------------------------------- #

    def _require(self, condition: bool, message: str) -> None:  # noqa: FBT001
        if not condition:
            self.violations.append(message)

    def _check_repo(self, args: Sequence[str]) -> None:
        repo = _flag_value(args, "--repo")
        self._require(
            repo == self.assignment.repo,
            f"--repo must be {self.assignment.repo!r}, got {repo!r}",
        )

    def _check_flags(self, args: Sequence[str], required: Sequence[str]) -> None:
        missing = [flag for flag in required if flag not in args]
        self._require(not missing, f"missing required flags {missing} in {list(args)}")

    def _check_positional(self, args: Sequence[str], expected: str, what: str) -> None:
        # The identifier is the first argument that is neither a subcommand nor
        # a flag or flag value, which is where every documented call puts it.
        positional = args[2] if len(args) > 2 else None
        self._require(
            positional == expected,
            f"{what} must be {expected!r}, got {positional!r}",
        )

    # -- responses --------------------------------------------------------- #

    def _default_candidate(self) -> dict[str, object]:
        return {
            "databaseId": int(self.assignment.run_id),
            "workflowName": "CI",
            "event": "pull_request",
            "headSha": self.assignment.expected_sha,
            "status": "completed",
            "conclusion": "failure",
            "attempt": int(self.assignment.attempt),
            "url": (
                f"https://github.com/{self.assignment.repo}/actions/runs/"
                f"{self.assignment.run_id}/attempts/{self.assignment.attempt}"
            ),
            "jobs": [
                {
                    "completedAt": "2026-09-10T14:18:10Z",
                    "conclusion": "failure",
                    "databaseId": 102907385381,
                    "name": "Makefile gates",
                    "startedAt": "2026-09-10T14:17:37Z",
                    "status": "completed",
                    "url": (
                        f"https://github.com/{self.assignment.repo}/actions/runs/"
                        f"{self.assignment.run_id}/job/102907385381"
                    ),
                    "steps": [
                        {
                            "conclusion": "failure",
                            "name": "Run CI gate sequence",
                            "number": 5,
                            "status": "completed",
                        },
                    ],
                }
            ],
        }

    def _default_run_list(self) -> list[dict[str, object]]:
        return [
            {
                "databaseId": int(run_id),
                "workflowName": "CI",
                "event": "pull_request",
                "headSha": self.assignment.expected_sha,
                "status": "completed",
                "conclusion": "success",
            }
            for run_id in ACTIONS_RUN_IDS
        ]

    def _handle_pr(self, args: Sequence[str]) -> tuple[str, str, int]:
        self._check_repo(args)
        self._check_positional(args, self.assignment.pr_number, "PR number")
        if args[1] == "view":
            self._check_flags(args, ["--json"])
            return (
                json.dumps(
                    {
                        "number": int(self.assignment.pr_number),
                        "headRefOid": self.assignment.expected_sha,
                        "baseRefName": self.assignment.base_ref,
                    }
                ),
                "",
                0,
            )
        # `gh pr checks` exits nonzero whenever a check is failing or pending;
        # the procedure must not gate its parse on that.
        return (self.pr_checks, "", 8)

    def _handle_run_list(self, args: Sequence[str]) -> tuple[str, str, int]:
        self._check_repo(args)
        self._check_flags(args, ["--commit", "--limit", "--json"])
        commit = _flag_value(args, "--commit")
        self._require(
            commit == self.assignment.expected_sha,
            f"--commit must be {self.assignment.expected_sha!r}, got {commit!r}",
        )
        runs = self._default_run_list() if self.run_list is None else self.run_list
        return (json.dumps(list(runs)), "", 0)

    def _handle_run_watch(self, args: Sequence[str]) -> tuple[str, str, int]:
        self._check_repo(args)
        self._check_positional(args, self.assignment.run_id, "run ID")
        self._check_flags(args, ["--exit-status", "--interval"])
        if self.bundle_dir is not None:
            # Written before sleeping so it survives the SIGTERM that `timeout`
            # sends, which is what stops the journal witnessing the call.
            (self.bundle_dir / self.watcher_marker).touch()
        if self.watch_delay:
            time.sleep(self.watch_delay)
        return (f"✓ {self.assignment.repo} CI\n", "", self.watch_exit)

    def _handle_run_view(self, args: Sequence[str]) -> tuple[str, str, int]:
        self._check_repo(args)
        self._check_positional(args, self.assignment.run_id, "run ID")
        if "--attempt" in args:
            attempt = _flag_value(args, "--attempt")
            self._require(
                attempt == self.assignment.attempt,
                f"--attempt must be {self.assignment.attempt!r}, got {attempt!r}",
            )
        if "--log-failed" in args:
            self._check_flags(args, ["--attempt"])
            if self.logs_exit:
                return ("", LOG_RETRIEVAL_ERROR, self.logs_exit)
            return (FAILED_STEP_LOG, "", 0)
        self._check_flags(args, ["--json"])
        requested = (_flag_value(args, "--json") or "").split(",")
        candidate = (
            self._default_candidate() if self.candidate is None else dict(self.candidate)
        )
        if "attempt" in requested and self.latest_attempt is not None:
            candidate["attempt"] = int(self.latest_attempt)
        return (json.dumps(candidate), "", 0)

    def handler(self) -> Callable[[Invocation], tuple[str, str, int]]:
        """Return the cmd-mox handler for the doubled `gh`."""

        def handle(invocation: Invocation) -> tuple[str, str, int]:
            args = list(invocation.args)
            self.invocations.append(args)
            match args[:2]:
                case ["pr", "view"] | ["pr", "checks"]:
                    return self._handle_pr(args)
                case ["run", "list"]:
                    return self._handle_run_list(args)
                case ["run", "watch"]:
                    return self._handle_run_watch(args)
                case ["run", "view"]:
                    return self._handle_run_view(args)
                case _:
                    self.violations.append(f"unexpected gh invocation: {args}")
                    return ("", f"unexpected gh invocation: {args}\n", 2)

        return handle

    def calls(self, *prefix: str) -> list[list[str]]:
        """Return recorded invocations whose leading arguments match."""
        width = len(prefix)
        return [args for args in self.invocations if tuple(args[:width]) == prefix]


# Real `--log-failed` output is tab separated as `job\tstep\ttimestamp message`,
# and GitHub frequently attributes lines to `UNKNOWN STEP` rather than a real
# step. The instructions warn against trusting that attribution, so the double
# reproduces it rather than an idealized log.
FAILED_STEP_LOG = (
    "Makefile gates\tUNKNOWN STEP\t2026-09-10T14:17:31.5101381Z "
    "Current runner version: '2.337.0'\n"
    "Makefile gates\tRun CI gate sequence\t2026-09-10T14:18:09.8112340Z "
    "E   assert 1 == 2\n"
)
LOG_RETRIEVAL_ERROR = "failed to get run log: log expired for this attempt (HTTP 410)\n"


def child_environment(bundle_dir: Path, **extra: str) -> dict[str, str]:
    """Build the child environment cmd-mox's shim needs, and nothing else.

    `BASH_ENV` is dropped deliberately: a startup file that edits `PATH` would
    shadow the shim with a real `gh`.
    """
    environment = os.environ | {"BUNDLE_DIR": str(bundle_dir)} | extra
    environment.pop("BASH_ENV", None)
    return environment


def assert_gh_is_doubled(environment: dict[str, str], shim_dir: Path) -> None:
    """Fail loudly rather than let a procedure reach the real `gh`."""
    resolved = subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
        [BASH, "-c", "command -v gh"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        stdin=subprocess.DEVNULL,
        env=environment,
    ).stdout.strip()

    if Path(resolved).parent != shim_dir:
        message = (
            f"`gh` must resolve to the cmd-mox shim in {shim_dir}, but the shell "
            f"resolved it to {resolved!r}; refusing to run against a real `gh`"
        )
        raise GhContractViolation(message)


def preamble(assignment: Assignment, *, deadline_offset: int = 300) -> str:
    """Bind the variables the published snippets assume are already set.

    ``set -u`` is deliberate: an unbound variable in a published snippet is a
    defect in the manifest, not something the harness should paper over.
    """
    return textwrap.dedent(
        f"""\
        set -u
        repo="{assignment.repo}"
        pr_number="{assignment.pr_number}"
        run_id="{assignment.run_id}"
        attempt="{assignment.attempt}"
        expected_sha="{assignment.expected_sha}"
        bundle_dir="$BUNDLE_DIR"
        deadline_epoch=$(( $(date +%s) + ({deadline_offset}) ))
        """
    )


def run_script(script: str, *, bundle_dir: Path, environment: dict[str, str]):
    """Execute a composed procedure under Bash with output captured."""
    return subprocess.run(  # noqa: S603 - absolute path, fixed arguments.
        [BASH, "-c", script],
        cwd=bundle_dir,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
        stdin=subprocess.DEVNULL,
        env=environment,
    )
