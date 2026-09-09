# Remove obsolete post-turn quality stop hook

- [x] Delete hooks/post-turn-quality-stop-hook.py and hooks/test_post_turn_quality_stop_hook.py
- [x] Update install-hooks to drop stop-hook install/validation/registration while preserving unrelated behaviour
  verify: ["bash -n via make shell-syntax-check (later in make ci)"]
- [x] Update Makefile: remove test-hooks target, obsolete comments, HOOK_TESTS wiring
- [x] Update pyproject.toml and mutation-testing workflow/config to drop hooks/ mutation setup
- [x] Update tests/test_workflow_contract.py (or remove) and any other workflow assertions
- [x] Update docs/users-guide.md and README.md with migration note to replacement repo
- [x] Update docs/developers-guide.md (test-hooks target, install-hooks section)
- [x] Run make ci and confirm suite passes
  verify: ["make ci: 70 passed (pytest), syntax/lint gates clean", "make lint: exit 0", "grep sweep: no obsolete references outside intentional migration notes"]
