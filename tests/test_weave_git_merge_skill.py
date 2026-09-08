"""Contract tests for the Weave Git merge skill's documentation.

Behavioural coverage of the procedures these documents describe lives in
`test_weave_git_merge_procedures.py`.
"""

from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = REPO_ROOT / "skills" / "weave-git-merge"
SKILL_PATH = SKILL_ROOT / "SKILL.md"
BEHAVIOUR_PATH = SKILL_ROOT / "references" / "behaviour.md"
AGENT_METADATA_PATH = SKILL_ROOT / "agents" / "openai.yaml"
REBASE_SKILL_PATH = REPO_ROOT / "skills" / "rebase" / "SKILL.md"


def _read(path: Path) -> str:
    """Read one repository contract file."""
    return path.read_text(encoding="utf-8")


def _mapping(document: str) -> dict[str, object]:
    """Parse a YAML document and require a mapping root."""
    parsed = yaml.safe_load(document)
    assert isinstance(parsed, dict), "expected a YAML mapping"
    return parsed


def _skill_frontmatter() -> tuple[dict[str, object], str]:
    """Return the Weave skill frontmatter and body."""
    content = _read(SKILL_PATH)
    assert content.startswith("---\n"), (
        "the Weave skill must open with the YAML frontmatter delimiter, "
        "with no leading prose"
    )
    parts = content.split("---", maxsplit=2)
    assert len(parts) == 3, "the Weave skill must have YAML frontmatter"
    body = parts[2]
    assert body.lstrip("\n").startswith("# Use Weave with Git\n"), (
        "the level-1 title must immediately follow the closing frontmatter "
        "delimiter"
    )
    return _mapping(parts[1]), body


def test_skill_discovery_metadata_describes_corruption_recovery() -> None:
    """Discovery metadata exposes the skill and its recovery purpose."""
    frontmatter, _ = _skill_frontmatter()
    description = frontmatter.get("description")

    assert frontmatter.get("name") == "weave-git-merge", (
        "the skill name must match its directory so discovery resolves it"
    )
    assert isinstance(description, str), "the skill must declare a description"
    assert "detecting structurally corrupt clean results" in description, (
        "discovery must advertise silent-corruption detection"
    )
    assert "bypassing Weave safely" in description, (
        "discovery must advertise the safe bypass route"
    )

    metadata = _mapping(_read(AGENT_METADATA_PATH))
    interface = metadata.get("interface")
    assert isinstance(interface, dict), "agent metadata must define interface"
    assert interface.get("display_name") == "Weave Git Merge", (
        "the OpenAI agent definition must expose the skill display name"
    )
    assert "$weave-git-merge" in str(interface.get("default_prompt")), (
        "the default prompt must invoke the weave-git-merge skill"
    )


def test_skill_requires_structural_checks_before_continue() -> None:
    """The workflow catches malformed output before Git records it."""
    _, skill = _skill_frontmatter()

    assert "python -m py_compile path/to/file.py" in skill, (
        "the workflow must show a per-file structural parse check"
    )
    assert "set -o pipefail" in skill, (
        "the piped check must fail when the producing command fails"
    )
    assert "ast.parse(sys.stdin.read())" in skill, (
        "the workflow must parse an index stage without touching the worktree"
    )
    assert "before `git add` or `git rebase --continue`" in skill, (
        "the check must be mandated before Git records the resolution"
    )


def test_skill_declares_bash_as_the_shell_for_every_example() -> None:
    """Bash-only syntax is covered by an explicit shell requirement."""
    _, skill = _skill_frontmatter()

    assert "Every shell example below requires Bash." in skill, (
        "the skill must state that its shell examples require Bash"
    )
    requirement, _, remainder = skill.partition(
        "Every shell example below requires Bash."
    )
    assert "```" not in requirement, (
        "the Bash requirement must precede every command block it governs"
    )
    assert "`set -o pipefail`" in remainder, (
        "the requirement must call out the Bash-only stage-validation option"
    )

    fences = [line for line in skill.splitlines() if line.startswith("```")]
    opening_fences = fences[::2]
    assert opening_fences, "the skill must contain fenced command blocks"
    assert all(fence == "```bash" for fence in opening_fences), (
        f"every command fence must be labelled bash, found {sorted(set(opening_fences))}"
    )


def test_skill_preserves_all_three_stage_inspection_commands() -> None:
    """The workflow keeps non-mutating inspection for every index stage."""
    _, skill = _skill_frontmatter()

    for stage in (1, 2, 3):
        assert f"git show :{stage}:path/to/file.py" in skill, (
            f"index stage {stage} must have a non-mutating inspection command"
        )
    assert (
        "stage 2 can\nalready contain an earlier silently corrupted replay"
    ) in skill, "the workflow must warn that stage 2 is not a trusted baseline"


def test_skill_guards_each_commit_in_a_multi_commit_rebase() -> None:
    """The workflow prevents an early clean corruption from cascading."""
    _, skill = _skill_frontmatter()

    assert "## Guard every replayed commit" in skill, (
        "the workflow must cover multi-commit rebases explicitly"
    )
    assert (
        "git rebase --exec 'python -m compileall -q -f path/to/package' origin/main"
    ) in skill, "each replayed Python commit must have an executable guard"
    assert "git rebase --exec 'cargo check --workspace' origin/main" in skill, (
        "Rust replay guidance must name cargo check as the honest workspace gate"
    )
    assert "`rustfmt` is a useful parser-level tripwire" in skill, (
        "the Rust guidance must distinguish parsing from type correctness"
    )
    assert (
        "Do not rely solely on the full test suite after the final commit" in skill
    ), "the workflow must reject end-of-rebase-only validation"


def test_skill_bypasses_ambient_weave_for_unattended_long_rebases() -> None:
    """Ambient global configuration is not treated as repository consent."""
    _, skill = _skill_frontmatter()

    assert "ambient selection is not repository consent" in skill, (
        "the policy must distinguish ambient configuration from repository opt-in"
    )
    assert "bypass Weave up front" in skill, (
        "unattended long replays must default to the built-in merge machinery"
    )
    assert "repository explicitly opts in through tracked attributes" in skill, (
        "tracked attributes must remain an explicit repository policy boundary"
    )
    assert "-c merge.conflictStyle=zdiff3" in skill, (
        "the built-in fallback must use the expected zdiff3 conflict style"
    )
    assert "primary checkout as a read-only coordination anchor" in skill, (
        "automation must not use the primary checkout as a rebase scratch surface"
    )


def test_skill_binds_rebase_evidence_to_candidate_identity() -> None:
    """History rewrites invalidate acceptance evidence for the old candidate."""
    _, skill = _skill_frontmatter()

    for variable in ("OLD_HEAD", "TARGET", "MERGE_BASE"):
        assert f"{variable}=$(git" in skill, (
            f"the workflow must record {variable} before rewriting history"
        )
    assert "evidence tied to `OLD_HEAD` is stale for acceptance" in skill, (
        "old gate and review evidence must not authorize the replayed candidate"
    )
    assert "rerun the candidate-bound\nchecks" in skill, (
        "the new candidate must receive fresh acceptance checks"
    )


def test_skill_reads_driver_stderr_and_supports_event_capture() -> None:
    """Clean auto-resolution output is retained as evidence, not discarded."""
    _, skill = _skill_frontmatter()

    assert "Never discard driver stderr" in skill, (
        "driver diagnostics must survive the Git operation"
    )
    assert "weave: 5 entities auto-resolved (conflict confidence)" in skill, (
        "the known auto-resolution signal must be named explicitly"
    )
    assert "|| true" not in skill, (
        "driver-evidence parsing must fail closed rather than masking a failed "
        "capture or an unreadable stderr file as a quiet success"
    )
    assert "2> >(" not in skill, (
        "stderr capture must use a checked redirection, not process "
        "substitution whose exit status is invisible to the caller"
    )
    assert "WEAVE_EVENT=1" in skill, (
        "supported Weave versions must expose one structured event per merge"
    )
    assert "weave-event:" in skill, (
        "the structured stderr prefix must be documented for log parsing"
    )
    assert "command-scoped" in skill, (
        "observability overrides must not leak across the agent session"
    )


def test_skill_requires_semantic_post_operation_audit() -> None:
    """A parser or compiler cannot be the final acceptance oracle."""
    _, skill = _skill_frontmatter()

    assert "## Audit the completed operation semantically" in skill, (
        "the workflow must require an audit beyond structural gates"
    )
    assert "Target-only paths are byte-identical" in skill, (
        "target changes untouched by the branch must survive exactly"
    )
    assert "Every deletion against the target" in skill, (
        "branch-touched files must receive explicit deletion review"
    )
    assert "Look for newly repeated blocks" in skill, (
        "the audit must look for clean duplicate reconstruction"
    )
    assert 'git diff --quiet "$TARGET" HEAD -- "$path"' in skill, (
        "the target-only byte-identity rule must have an executable check"
    )
    assert "while IFS= read -r -d '' path; do" in skill, (
        "the check must bind each path from the set difference before "
        "comparing it, or an unbound `$path` would widen it to the whole tree"
    )
    assert "comm -z -13" in skill, (
        "the target-only path set must be a real set difference of the two "
        "NUL-delimited manifests"
    )
    assert "parsed, compiled, and passed\ntests" in skill, (
        "the workflow must retain the semantic-corruption counterexample"
    )


def test_skill_runs_weave_check_only_when_the_installed_version_supports_it() -> None:
    """Weave's checker is versioned evidence rather than an assumed command."""
    _, skill = _skill_frontmatter()

    assert "## Run Weave's own post-merge checker when supported" in skill, (
        "the workflow must make post-merge self-checking explicit"
    )
    assert "weave --version" in skill, (
        "the operation receipt must identify the CLI version"
    )
    assert "weave check --help" in skill, (
        "the workflow must feature-probe the checker before invoking it"
    )
    assert "\nweave check\n" in skill, (
        "the workflow must execute the checker on its own command line; a bare "
        "substring check would be satisfied by the `--help` probe alone"
    )
    assert "`weave_check` tool" in skill, (
        "agents using MCP must be told about the equivalent read-only tool"
    )
    assert "Neither interface replaces" in skill, (
        "Weave self-validation must not replace the independent semantic audit"
    )


def test_skill_declares_andon_triggers() -> None:
    """Known evidence failures stop branch advancement before repair guessing."""
    _, skill = _skill_frontmatter()

    assert "## Andon triggers" in skill, "the workflow must name stop-the-line events"
    for trigger in (
        "target-only path differs",
        "unexplained deletion",
        "new duplication",
        "versions disagree unexpectedly",
        "recovery evidence omits staged, unstaged, or intended untracked work",
    ):
        assert trigger in skill, f"the andon list must include {trigger!r}"
    assert "not an instruction to guess a repair" in skill, (
        "an andon event must preserve evidence before remediation"
    )


def test_skill_requires_complete_recovery_evidence_before_destructive_git() -> None:
    """Recovery coverage includes untracked files and neutralizes display diffs."""
    _, skill = _skill_frontmatter()

    assert "staged,\nunstaged, and intended untracked files" in skill, (
        "destructive Git operations must account for every local-state class"
    )
    assert "--no-ext-diff --no-textconv --binary" in skill, (
        "native recovery diffs must bypass display and text-conversion drivers"
    )
    assert "patch that applies successfully does\nnot prove" in skill, (
        "applicability must not be confused with recovery completeness"
    )


def test_skill_keeps_operation_specific_global_fallbacks() -> None:
    """Each interrupted Git operation is aborted before its retry."""
    _, skill = _skill_frontmatter()

    required_commands = (
        "git rebase --abort",
        'git -c core.attributesFile=/dev/null rebase "$TARGET"',
        "git merge --abort",
        "git -c core.attributesFile=/dev/null merge <same-original-arguments>",
        "git cherry-pick --abort",
        "git -c core.attributesFile=/dev/null cherry-pick <same-original-arguments>",
    )
    for command in required_commands:
        assert command in skill, (
            f"the fallback must document `{command}` so each operation is "
            "aborted before its own retry"
        )
    assert "git -c core.attributesFile=/dev/null rebase origin/main" not in skill, (
        "the retry must resolve the recorded target, not re-read a remote ref "
        "that may have moved since the candidate identities were recorded"
    )


def test_skill_recovers_a_completed_operation_by_resetting_the_candidate() -> None:
    """A clean driver exit leaves nothing to abort, so recovery must reset."""
    _, skill = _skill_frontmatter()

    assert 'git reset --hard "$OLD_HEAD"' in skill, (
        "an operation the driver's clean exit allowed to complete must be "
        "recovered by restoring the recorded candidate"
    )
    assert "state those abort commands need is gone and they fail" in skill, (
        "the workflow must say why `--abort` cannot recover a completed "
        "operation, not merely offer an alternative"
    )
    assert "Only after recovery evidence is verified" in skill, (
        "the destructive reset must be ordered after recovery evidence, "
        "because it discards staged, unstaged, and untracked work"
    )


def test_skill_distinguishes_attribute_sources_and_bypass_scopes() -> None:
    """The scope matrix preserves the distinct Git attribute levers."""
    _, skill = _skill_frontmatter()

    assert "reports only effective attribute values" in skill, (
        "the workflow must warn that check-attr hides the attribute source"
    )
    assert "`git config --path --get core.attributesFile`" in skill, (
        "the workflow must show how to locate the global attributes file"
    )
    assert "prints nothing and\nexits non-zero when the setting is absent" in skill, (
        "an unset core.attributesFile must not read as an absent global rule"
    )
    assert "| Global | Configured global attributes file" in skill, (
        "the scope matrix must cover the global attributes file"
    )
    assert "| Tracked | Repository `.gitattributes`" in skill, (
        "the scope matrix must cover tracked repository attributes"
    )
    assert "| Clone-local | `.git/info/attributes`" in skill, (
        "the scope matrix must cover clone-local attributes"
    )
    assert "path/to/file.py !merge" in skill, (
        "the workflow must show the per-path merge-driver opt-out"
    )
    assert (
        "restore `.git/info/attributes` only after the operation completes" in skill
    ), "the clone-local bypass must not be reverted mid-operation"
    assert "`/dev/null` alone cannot override those rules" in skill, (
        "the workflow must state the limits of the global-file override"
    )


def test_rebase_skill_routes_garbled_results_to_weave_recovery() -> None:
    """The general rebase workflow points failures to the detailed fallback."""
    rebase_skill = _read(REBASE_SKILL_PATH)

    assert "# Rebase the current branch" in rebase_skill, (
        "the rebase skill must keep its level-1 title"
    )
    assert (
        "[weave-git-merge recovery and built-in-merge fallback]"
        "(../weave-git-merge/SKILL.md#recover-safely)"
    ) in rebase_skill, "the rebase skill must link to the Weave recovery section"
    assert "before continuing the rebase" in rebase_skill, (
        "recovery must happen before the rebase is allowed to continue"
    )


def test_rebase_skill_keeps_patch_recovery_clear_of_external_diff_drivers() -> None:
    """Patch-based recovery names the flag that restores a usable diff."""
    rebase_skill = _read(REBASE_SKILL_PATH)

    assert "git diff --no-ext-diff" in rebase_skill, (
        "patch generation must suppress an external diff driver"
    )
    assert "`diff.external` or `GIT_EXTERNAL_DIFF`" in rebase_skill, (
        "the guidance must name both ways an external diff driver is configured"
    )
    assert "error: No valid patches in input" in rebase_skill, (
        "the symptom must be searchable from the error git apply prints"
    )
    assert "Confirm a saved patch starts with\n`diff --git`" in rebase_skill, (
        "the reader must be told how to check a patch before applying it"
    )
    assert "prefer\n`git stash show -p` when the work to recover is a stash" in (
        rebase_skill
    ), "stash recovery must point at the command that is already safe"


def test_behaviour_reference_records_known_clean_exit_corruptions() -> None:
    """The reference keeps all observed corruption classes searchable."""
    behaviour = _read(BEHAVIOUR_PATH)

    assert "conflict-free replicated data type (CRDT)" in behaviour, (
        "the reference must expand CRDT on first use"
    )
    assert (
        "Do not generalize the import-addition case to import relocation" in behaviour
    ), "the reference must scope the safe import case narrowly"
    assert "non-parsing Python despite a clean exit" in behaviour, (
        "the reference must record the observed Python silent corruption"
    )
    assert "belongs on the line-level-fallback path" in behaviour, (
        "the reference must state where import relocation should be handled"
    )
    for heading in (
        "### Rust cfg-gated sibling replacement",
        "### Rust re-export duplication",
        "### Markdown doubled blank lines",
    ):
        assert heading in behaviour, f"the reference must retain {heading!r}"
    assert "parsed, compiled, and passed the test suite" in behaviour, (
        "the Rust semantic corruption must explicitly defeat structural gates"
    )


def test_behaviour_reference_documents_observability_and_weave_check() -> None:
    """The reference names both driver evidence channels and the checker."""
    behaviour = _read(BEHAVIOUR_PATH)

    assert "weave: 5 entities auto-resolved (conflict confidence)" in behaviour, (
        "the known stderr signal must remain searchable"
    )
    assert "WEAVE_EVENT=1" in behaviour and "weave-event:" in behaviour, (
        "structured per-merge events must be documented"
    )
    assert "weave --version" in behaviour and "weave-driver --version" in behaviour, (
        "CLI and driver provenance must both be recorded"
    )
    assert "Weave 0.5.1 and later provide `weave check`" in behaviour, (
        "the expected estate baseline must expose the post-merge checker"
    )
    assert "`weave_check` tool" in behaviour, (
        "the MCP equivalent must be discoverable by agents"
    )
