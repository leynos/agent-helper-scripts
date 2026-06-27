SHELL := /usr/bin/env
.SHELLFLAGS := bash -c

ROOT_SHELL_SCRIPTS := \
	$(wildcard add-* apt-* get-* install-* rust-*) \
	bootstrap-adapters \
	bootstrap-common \
	markdownlint \
	mdformat-all \
	notdeadyet \
	python-setup
SHELL_SCRIPTS := $(sort $(ROOT_SHELL_SCRIPTS) $(wildcard bin/*.sh))
HOME_PHASE_HELPERS != awk '\
	/^[[:space:]]*SELECTED_TOOLS=[(][[:space:]]*$$/ { in_tools=1; next } \
	in_tools && /^[[:space:]]*[)][[:space:]]*$$/ { in_tools=0; next } \
	in_tools && /^[[:space:]]*[[:alnum:]_-]+[[:space:]]*$$/ { print $$1 } \
	/SELECTED_TOOLS[+][=][(]/ { \
		line=$$0; \
		sub(/^.*SELECTED_TOOLS[+][=][(]/, "", line); \
		sub(/\).*$$/, "", line); \
		if (line != "") print line; \
	} \
' bootstrap-common
HOME_PHASE_SCRIPTS := rust-entrypoint-home $(HOME_PHASE_HELPERS)
HOME_PHASE_BOUNDARY_PATTERN := ^[[:space:]]*(apt-get|apt-update-if-stale|sudo|install|realpath|ln)([[:space:]]|$$)|/etc/apt|/usr/bin/ld|update-ca-certificates|/var/lib/apt
PYTHON_SCRIPTS := $(sort $(wildcard hooks/*.py tests/*.py))
PYTEST := uv run --group dev python -m pytest
HOOK_TESTS := $(sort $(wildcard hooks/test_*.py))
REPO_TESTS := $(sort $(wildcard tests/test_*.py))
ENTRYPOINT_TESTS := $(filter tests/test_rust_entrypoints.py,$(REPO_TESTS))
TEST_TARGETS := $(HOOK_TESTS) $(REPO_TESTS)

# Test targets:
# - test-hooks: post-turn hook behavior and git-state decisions.
# - test-entrypoints: rust-entrypoint process tests using cuprum and cmd-mox.
# - test: full pytest suite for all repository tests.
# - ci: complete CI/CD gate sequence used by GitHub Actions.
.PHONY: all clean check-fmt lint typecheck syntax-check shell-syntax-check check-home-phase-boundary test-hooks test-entrypoints test ci

all: ci

ci: check-fmt lint typecheck test

clean:
	@echo "clean: nothing to clean"

check-fmt:
	@echo "check-fmt: no formatter configured"

syntax-check:
	@python3 -m py_compile $(PYTHON_SCRIPTS)

shell-syntax-check:
	@bash -n $(SHELL_SCRIPTS)

check-home-phase-boundary:
	@awk 'BEGIN { forbidden = "$(HOME_PHASE_BOUNDARY_PATTERN)" } /^[[:space:]]*#/ { next } $$0 ~ forbidden { printf "%s:%d:%s\n", FILENAME, FNR, $$0; found=1 } END { exit found ? 1 : 0 }' $(HOME_PHASE_SCRIPTS)

lint: syntax-check shell-syntax-check check-home-phase-boundary

typecheck: syntax-check
	@echo "typecheck: no static type checker configured (ran syntax-check)"

test:
	@$(PYTEST) $(TEST_TARGETS) -v

test-hooks:
	@$(PYTEST) $(HOOK_TESTS) -v

test-entrypoints:
	@$(PYTEST) $(ENTRYPOINT_TESTS) -v
