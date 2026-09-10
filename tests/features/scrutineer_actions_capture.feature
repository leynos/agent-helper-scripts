Feature: Scrutineer captures GitHub Actions evidence
  The scrutineer sub-agent's instructions publish three shell procedures for
  observing a workflow run and capturing its evidence: a deadline-bounded
  `gh run watch`, an attempt-specific `gh run view` snapshot, and a
  `--log-failed` retrieval.

  These scenarios extract those procedures from `agents/subagents.yml` and run
  them verbatim against a doubled `gh`, so the manifest and the specification
  cannot drift apart. The double replays representative real `gh` output,
  including the `UNKNOWN STEP` attribution that `--log-failed` genuinely emits.

  Background:
    Given the manifest publishes the Actions capture procedures

  Scenario: A failing watcher still yields metadata and failure logs
    Given a run that completed with conclusion "failure"
    And the watcher exits with status 1
    When the capture procedures run with 300 seconds of budget remaining
    Then the watcher status is recorded as 1
    And the attempt snapshot is captured
    And the recorded conclusion is "failure"
    And the failed-step log is captured

  Scenario: An exhausted budget starts no watcher at all
    Given a run that completed with conclusion "failure"
    When the capture procedures run with -5 seconds of budget remaining
    Then the watcher status is recorded as 124
    And no watcher was started
    And the attempt snapshot is captured

  Scenario: A watcher outliving its budget is stopped by the deadline
    Given a run that completed with conclusion "failure"
    And the watcher hangs for 30 seconds
    When the capture procedures run with 1 seconds of budget remaining
    Then the watcher status is recorded as 124
    And the procedures finish before the watcher would have
    And the attempt snapshot is captured

  Scenario: A log retrieval failure stays separate from the run's conclusion
    Given a run that completed with conclusion "failure"
    And the watcher exits with status 1
    And failed-step log retrieval exits with status 1
    When the capture procedures run with 300 seconds of budget remaining
    Then the log retrieval status is recorded as 1
    And the watcher status is recorded as 1
    And the recorded conclusion is "failure"
    And the retrieval error is preserved in the bundle

  Scenario: A successful run manufactures no failure evidence
    Given a run that completed with conclusion "success"
    When the capture procedures run with 300 seconds of budget remaining
    Then every recorded status is zero
    And the recorded conclusion is "success"

  Scenario Outline: The snapshot survives any watcher outcome
    Given a run that completed with conclusion "failure"
    And the watcher exits with status <watcher_status>
    When the capture procedures run with 300 seconds of budget remaining
    Then the watcher status is recorded as <watcher_status>
    And the attempt snapshot is captured

    Examples:
      | watcher_status |
      | 0              |
      | 1              |
      | 124            |
      | 143            |
