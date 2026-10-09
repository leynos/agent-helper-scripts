"""Exercise documented Git operations and section-local delivery obligations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
REBASE = ROOT / "skills/pr-babysitting/references/rebase.md"
ASSESSMENT = ROOT / "skills/pr-babysitting/references/execplan-assessment.md"
SKILL = ROOT / "skills/pr-babysitting/SKILL.md"


def section(text: str, heading: str) -> str:
    """Find one second-level section without accepting guards moved elsewhere."""
    matches = re.findall(r"^## " + re.escape(heading) + r"\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert len(matches) == 1, f"expected unique section: {heading}"
    return " ".join(matches[0].split())


def git_example(marker: str) -> str:
    """Execute a uniquely selected real Bash fence, failing closed on ambiguity."""
    fences = re.findall(r"^```bash\n(.*?)^```$", REBASE.read_text(), re.M | re.S)
    matches = [fence for fence in fences if marker in fence]
    assert len(matches) == 1, f"expected unique Git example containing {marker}"
    return matches[0]


@dataclass
class GitFixture:
    """A file-transport-only repository with no inherited credentials or config."""

    root: Path
    work: Path
    env: dict[str, str]

    def git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        """Run local Git and return its bounded textual result."""
        result = subprocess.run(
            ["/usr/bin/git", *args], cwd=cwd or self.work, env=self.env,
            text=True, capture_output=True, check=False, timeout=30,
        )
        if check:
            assert result.returncode == 0, f"git {args} failed: {result.stderr}"
        else:
            assert result.returncode != 0, f"git {args} unexpectedly succeeded"
        return result.stdout.strip()

    def commit(self, path: str, contents: str, message: str) -> str:
        """Commit one fixture file with a deterministic local identity."""
        (self.work / path).write_text(contents)
        self.git("add", "--", path)
        self.git("commit", "-m", message)
        return self.git("rev-parse", "HEAD")

    def example(self, marker: str, **variables: str) -> subprocess.CompletedProcess[str]:
        """Run the actual documented fence under its check-each-command precondition."""
        return subprocess.run(
            ["/bin/bash", "-e", "-c", git_example(marker)], cwd=self.work,
            env=self.env | variables, text=True, capture_output=True, check=False, timeout=30,
        )


@pytest.fixture
def local_git(tmp_path: Path) -> GitFixture:
    """Provide separate target and push remotes without consulting host configuration."""
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
        "PATH": "/usr/bin:/bin", "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ALLOW_PROTOCOL": "file",
        "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "Fixture Author",
        "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
        "GIT_COMMITTER_NAME": "Fixture Author",
        "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    }
    work = tmp_path / "work"
    work.mkdir()
    fixture = GitFixture(tmp_path, work, env)
    fixture.git("init", "--initial-branch=main")
    fixture.commit("manifest", "base\n", "base")
    for remote in ("target", "push"):
        bare = tmp_path / f"{remote}.git"
        fixture.git("init", "--bare", "--initial-branch=main", str(bare))
        fixture.git("remote", "add", remote, str(bare))
        fixture.git("push", remote, "main")
    return fixture


def test_fetch_example_freezes_nondefault_target_on_distinct_remote(local_git: GitFixture) -> None:
    """The release target is fetched from its repository, not from the push upstream."""
    fixture = local_git
    fixture.git("switch", "-c", "release/next")
    release = fixture.commit("manifest", "target-release\n", "release target")
    fixture.git("push", "target", "release/next")
    fixture.git("update-ref", "-d", "refs/remotes/target/release/next")
    fixture.git("switch", "-c", "feature", "main")
    feature = fixture.commit("manifest", "feature\n", "feature head")
    fixture.git("push", "push", "feature")
    script = git_example('git check-ref-format') + '\nprintf "%s\\n%s\\n" "$TARGET_REF" "$TARGET"\n'
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", script], cwd=fixture.work,
        env=fixture.env | {"target_remote": "target", "target_branch": "release/next"},
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["refs/remotes/target/release/next", release], "freeze must select actual release target"
    assert release != feature, "fixture must distinguish target and feature"
    assert fixture.git("rev-parse", "main") != release, "fixture must distinguish default and release"


def test_lock_restore_example_preserves_combined_manifest_during_replay(local_git: GitFixture) -> None:
    """Target lock restoration resolves the index without discarding feature requirements."""
    fixture = local_git
    base = fixture.commit("package.lock", "base lock\n", "base lock")
    fixture.git("switch", "-c", "feature")
    fixture.commit("manifest", "feature dependency\n", "feature requirement")
    feature = fixture.commit("package.lock", "feature lock\n", "feature lock")
    fixture.git("switch", "-c", "release", base)
    fixture.commit("manifest", "target dependency\n", "target requirement")
    target = fixture.commit("package.lock", "target lock\n", "target lock")
    fixture.commit("package.lock", "earlier replay lock\n", "earlier replay")
    fixture.git("cherry-pick", feature, check=False)
    assert fixture.git("ls-files", "--unmerged", "package.lock"), "fixture must have a real replay lock conflict"
    combined = "target dependency\nfeature dependency\n"
    (fixture.work / "manifest").write_text(combined)
    fixture.git("add", "manifest")
    result = fixture.example("git restore", TARGET=target, lockfile="package.lock")
    assert result.returncode == 0, result.stderr
    assert fixture.git("show", ":package.lock") == "target lock", "index baseline must come from frozen target"
    assert (fixture.work / "package.lock").read_text() == "target lock\n", "worktree baseline must match target"
    assert (fixture.work / "manifest").read_text() == combined, "combined manifest must survive restoration"
    assert not fixture.git("ls-files", "--unmerged"), "lock conflict must be resolved in index"


@pytest.mark.parametrize("concurrent_writer", [False, True], ids=["accepted-lease", "stale-lease"])
def test_push_example_uses_recorded_lease_without_overwriting_writer(
    local_git: GitFixture, concurrent_writer: bool
) -> None:
    """A rewrite publishes only against the observed head; stale leases preserve other work."""
    fixture = local_git
    fixture.git("switch", "-c", "feature")
    observed = fixture.commit("feature", "original\n", "original feature")
    fixture.git("push", "push", "feature")
    (fixture.work / "feature").write_text("rewritten\n")
    fixture.git("add", "feature")
    fixture.git("commit", "--amend", "-m", "rewritten feature")
    candidate = fixture.git("rev-parse", "HEAD")
    remote_head = observed
    if concurrent_writer:
        writer = fixture.root / "writer"
        fixture.git("clone", "--branch", "feature", str(fixture.root / "push.git"), str(writer))
        (writer / "concurrent").write_text("other writer\n")
        fixture.git("add", "concurrent", cwd=writer)
        fixture.git("commit", "-m", "concurrent writer", cwd=writer)
        fixture.git("push", "origin", "feature", cwd=writer)
        remote_head = fixture.git("rev-parse", "HEAD", cwd=writer)
    result = fixture.example(
        "--force-with-lease", head_branch="feature", EXPECTED_REMOTE_HEAD=observed,
        push_remote="push", CANDIDATE=candidate,
    )
    actual = fixture.git("ls-remote", "push", "refs/heads/feature").split()[0]
    if concurrent_writer:
        assert result.returncode != 0, "stale recorded lease must reject publication"
        assert actual == remote_head, "rejected lease must preserve concurrent commit"
    else:
        assert result.returncode == 0, result.stderr
        assert actual == candidate, "accepted lease must publish exact candidate"


def assessment_contract(assessment: str, skill: str) -> None:
    """Check obligations where they control readiness, requests, and publication."""
    applicability = section(assessment, "Applicability and ownership")
    assert "Apply the proof assessment whenever implementation introduces or materially changes a proof" in applicability, "proof applicability must remain in ownership section"
    assert "require passing applicable deterministic correctness and quality gates" in applicability, "request prerequisites must require passing gates"
    assert "for the published candidate" in applicability, "gates must bind to published candidate"
    assert "Verify remote parity" in applicability, "request prerequisites must verify publication"
    routing = section(assessment, "Comment routing")
    assert "two initial assessment comments below are explicit, narrow exceptions" in routing, "initial manual exceptions must stay narrow"
    assert "assigned token procedure" in routing and "`shuf`" in routing, "initial comments must use assigned token route"
    assert "All subsequent whole-assessment retries, fresh full or incremental reviews, and review-resume requests use `comenq-coderabbit`" in routing, "later assessments must use managed queue"
    readiness = section(assessment, "Readiness and later changes")
    assert "Both applicable assessments must clear for the accepted candidate before its draft-to-ready transition" in readiness, "applicable assessments must precede readiness"
    assert "An already-ready PR stays ready; obtain missing assessments before merge" in readiness, "missing assessment must block merge without redrafting"
    assert "Do not set the PR back to draft" in readiness, "redrafting prohibition must remain in readiness section"
    parent_ready = section(skill, "5. Assess applicable delivery gates, then mark green drafts ready")
    assert "all applicable pre-readiness assessments hold" in parent_ready, "parent readiness condition must include assessments"
    assert "An already-ready PR remains ready while missing or invalidated assessments block merge" in parent_ready, "parent must preserve ready state and merge blocker"
    merge = section(skill, "10. End cosmetic review churn, then squash-merge safely")
    assert "Applicable ExecPlan completeness/correctness and proof-specific assessments cover the accepted candidate, with no unresolved substantive concern" in merge, "merge checklist must require candidate-bound assessments"


def test_assessment_guards_control_the_real_workflow_sections() -> None:
    """Readiness and merge guards must live in their controlling documentation sections."""
    assessment_contract(ASSESSMENT.read_text(), SKILL.read_text())


@pytest.mark.parametrize(
    ("document", "old", "new", "move"),
    [
        ("assessment", "Both applicable assessments must clear", "Both applicable assessments need not clear", False),
        ("assessment", "An already-ready PR stays ready; obtain missing assessments before merge.", "", False),
        ("assessment", "for the\npublished candidate.", "for any old candidate.", False),
        ("assessment", "All subsequent whole-assessment retries, fresh full or incremental reviews,\nand review-resume requests use `comenq-coderabbit`,", "Later retries use manual comments,", False),
        ("assessment", "Both applicable assessments must clear for\nthe accepted candidate before its draft-to-ready transition.", "", True),
        ("skill", "all\napplicable pre-readiness assessments hold", "no assessments hold", False),
        ("skill", "An already-ready PR remains ready while\nmissing or invalidated assessments block merge.", "", True),
        ("skill", "7. Applicable ExecPlan completeness/correctness and proof-specific assessments\n   cover the accepted candidate, with no unresolved substantive concern.", "", True),
    ],
    ids=["inverted-readiness", "removed-ready-preservation", "stale-publication", "manual-retry", "moved-readiness", "parent-waiver", "moved-parent-preservation", "moved-merge-guard"],
)
def test_assessment_contract_rejects_missing_inverted_or_misplaced_guards(
    document: str, old: str, new: str, move: bool
) -> None:
    """Negative controls prove guards cannot be waived or pasted into an unrelated section."""
    assessment, skill = ASSESSMENT.read_text(), SKILL.read_text()
    source = assessment if document == "assessment" else skill
    assert source.count(old) == 1, "mutation fixture must identify one actual controlling clause"
    mutated = source.replace(old, new, 1)
    if move:
        mutated += "\n## Unrelated notes\n\n" + old + "\n"
    with pytest.raises(AssertionError, match="must|prerequisites"):
        assessment_contract(mutated if document == "assessment" else assessment,
                            mutated if document == "skill" else skill)


def test_absent_renamed_deleted_lockfiles_require_explicit_planning() -> None:
    """The baseline command cannot substitute for deciding changed lockfile intent."""
    packaging = section(REBASE.read_text(), "Packaging lockfiles")
    assert "new, removed, renamed, absent at the target" in packaging, "changed lockfile paths must be handled explicitly"
    assert "inspect that intent and record a plan" in packaging, "absent or renamed lockfiles require a resolution plan"
    assert "do not invent a target file or resurrect a deliberate deletion" in packaging, "baseline must not resurrect deleted target files"
    assert "Regenerate sooner as well if a per-replay gate requires a coherent manifest/lock pair" in packaging, "per-replay gates must have coherent locks"


@pytest.mark.parametrize("document", ["## Other\ncontent\n", "## Wanted\none\n## Wanted\ntwo\n"],
                         ids=["missing", "ambiguous"])
def test_section_extraction_rejects_missing_or_duplicate_controls(document: str) -> None:
    """A malformed document cannot satisfy section-local guards accidentally."""
    with pytest.raises(AssertionError, match="expected unique section: Wanted"):
        section(document, "Wanted")


def test_rebase_gate_example_runs_four_checks_in_documented_order(tmp_path: Path) -> None:
    """The actual gate fence invokes each required target sequentially with a make double."""
    make = tmp_path / "make"
    make.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MAKE_LOG"\n')
    make.chmod(0o755)
    log = tmp_path / "make-calls"
    result = subprocess.run(
        ["/bin/bash", "-e", "-c", git_example("make check-fmt")],
        env={"PATH": str(tmp_path), "MAKE_LOG": str(log)},
        text=True, capture_output=True, check=False, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert log.read_text().splitlines() == ["check-fmt", "test", "typecheck", "lint"], "rebase example must invoke all four gates sequentially in its documented order"
