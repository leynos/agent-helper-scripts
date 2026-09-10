Feature: Scrutineer resolves and verifies Actions candidates
  Before it watches anything, the scrutineer sub-agent must work out *which*
  runs an assignment refers to. The manifest publishes that resolution as
  executable procedures: PR candidates from `gh pr view` and `gh pr checks`,
  commit-scoped candidates from `gh run list --commit`, and verification of
  every candidate with `gh run view` before it may enter the evidence steps.

  These scenarios extract those procedures from `agents/subagents.yml` and run
  them verbatim against a `gh` double that validates the repository, PR number,
  run ID, attempt, commit SHA, and required flags of every call. Addressing the
  wrong run is therefore a failure rather than something a lenient double would
  wave through.

  Background:
    Given the manifest publishes the Actions monitoring procedures

  Scenario: PR candidates come from the check links, deduplicated
    Given a pull request whose checks include two jobs of the same run
    When the PR candidate resolution procedure runs
    Then the candidate runs are exactly "34537498828, 34537499940"
    And the pull request head and base are recorded

  Scenario: Non-Actions checks are classified, not mistaken for runs
    Given a pull request whose checks include two jobs of the same run
    When the PR candidate resolution procedure runs
    Then the non-Actions checks are recorded as "Kody Code Review, Sourcery review, CodeRabbit"
    And no non-Actions check appears among the candidate runs

  Scenario: A failing or pending check set still yields candidates
    Given a pull request whose checks include two jobs of the same run
    When the PR candidate resolution procedure runs
    Then the candidate runs are exactly "34537498828, 34537499940"

  Scenario: Commit-scoped assignments resolve by exact commit
    Given runs exist for the expected commit
    When the commit candidate resolution procedure runs
    Then the run list was requested for the expected commit
    And the candidate runs are exactly "34537498828, 34537499940"
    And no missing-candidates note is written

  Scenario: A commit with no runs yet is recorded as missing, not successful
    Given no runs exist for the expected commit
    When the commit candidate resolution procedure runs
    Then a missing-candidates note names the expected commit
    And the candidate runs are empty

  Scenario: A candidate matching the expected commit verifies
    Given a candidate run for event "push" at the expected commit
    When the candidate verification procedure runs
    Then the candidate state is "verified"
    And the candidate was verified before any watch or evidence call

  Scenario: A pull_request candidate records the synthetic merge association
    Given a candidate run for event "pull_request" at the expected commit
    When the candidate verification procedure runs
    Then the candidate state is "pr-head-synthetic-merge"

  Scenario: A candidate at a different commit is refused
    Given a candidate run for event "push" at commit "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    When the candidate verification procedure runs
    Then the candidate state is "sha-mismatch"

  Scenario: A rerun since the evidence was captured is reported as superseded
    Given the latest attempt is now "3"
    When the attempt recheck procedure runs
    Then the evidence is marked superseded by attempt "3"

  Scenario: An unchanged attempt is not marked superseded
    Given the latest attempt is now "2"
    When the attempt recheck procedure runs
    Then the evidence is not marked superseded

  Scenario: A monitoring-only assignment runs no gates and no review
    Given a pull request whose checks include two jobs of the same run
    When the full monitoring-only workflow runs
    Then no local gate or review command was invoked
    And every gh call addressed the assigned repository and run
