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
PYTHON_SCRIPTS := $(sort $(wildcard hooks/*.py scripts/*.py tests/*.py))
PYTEST := uv run --group dev python -m pytest
TYPOS_VERSION ?= 1.48.0
TYPOS := uv tool run typos@$(TYPOS_VERSION)
REPO_TESTS := $(sort $(wildcard tests/test_*.py))
ENTRYPOINT_TESTS := $(filter tests/test_rust_entrypoints.py,$(REPO_TESTS))
TEST_TARGETS := $(REPO_TESTS)
SKILL_DIRS ?= $(sort $(dir $(wildcard skills/*/SKILL.md)))
SKILLS_REF := uv run --group dev skills-ref
YAMLLINT := uv run --group dev yamllint
SKILL_YAMLLINT_CONFIG := {extends: default, rules: {line-length: disable}}
# The Markdown gate calls the linter directly. The repository's own
# `markdownlint` wrapper covers the case where nothing has installed
# markdownlint-cli2, and the shared baseline this repository is moving to
# provisions it globally.
MDLINT ?= markdownlint-cli2
NIXIE ?= nixie

# Test targets:
# - test-entrypoints: rust-entrypoint process tests using cuprum and cmd-mox.
# - test: full pytest suite for all repository tests.
# - ci: complete CI/CD gate sequence used by GitHub Actions.
.PHONY: all clean check-fmt fmt markdownlint nixie lint typecheck syntax-check shell-syntax-check check-home-phase-boundary skill-frontmatter-lint skill-manifest-validate skill-manifest-check spelling test-entrypoints test ci

all: ci

# Every gate `make ci` runs. CI supplies the Markdown gate with the
# markdownlint-cli2 action, which brings its own linter, so the workflow sets
# CI_SKIP_MARKDOWNLINT=1 rather than repeating the list and letting the two
# drift apart when a gate is added here.
CI_GATES := check-fmt markdownlint lint typecheck test
ifeq ($(CI_SKIP_MARKDOWNLINT),1)
CI_GATES := $(filter-out markdownlint,$(CI_GATES))
endif

ci: $(CI_GATES)
	+$(MAKE) spelling

# Fail early with an actionable message when a gate's CLI tool is absent.
define ensure-tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

clean:
	@echo "clean: nothing to clean"

check-fmt:
	@echo "check-fmt: no formatter configured"

fmt:
	@mdformat-all

markdownlint:
	$(call ensure-tool,$(MDLINT))
	@$(MDLINT) '**/*.md'

# Not part of `ci`: nixie renders through an external Mermaid CLI (merman-cli or
# mmdc plus Chromium), which the CI runner does not provide.
nixie:
	$(call ensure-tool,$(NIXIE))
	@$(NIXIE) --no-sandbox

syntax-check:
	@python3 -m py_compile $(PYTHON_SCRIPTS)

shell-syntax-check:
	@bash -n $(SHELL_SCRIPTS)

check-home-phase-boundary:
	@awk 'BEGIN { forbidden = "$(HOME_PHASE_BOUNDARY_PATTERN)" } /^[[:space:]]*#/ { next } $$0 ~ forbidden { printf "%s:%d:%s\n", FILENAME, FNR, $$0; found=1 } END { exit found ? 1 : 0 }' $(HOME_PHASE_SCRIPTS)

lint: syntax-check shell-syntax-check check-home-phase-boundary skill-manifest-check

skill-frontmatter-lint:
	@set -euo pipefail; for skill_dir in $(SKILL_DIRS); do \
		skill_file="$${skill_dir%/}/SKILL.md"; \
		echo "yamllint $$skill_file frontmatter"; \
		awk 'NR == 1 { if ($$0 != "---") exit 1; print; next } $$0 == "---" { found = 1; print; exit } { print } END { if (!found) exit 1 }' "$$skill_file" | $(YAMLLINT) -d '$(SKILL_YAMLLINT_CONFIG)' -; \
	done

skill-manifest-validate:
	@set -eu; for skill_dir in $(SKILL_DIRS); do \
		echo "skills-ref validate $$skill_dir"; \
		$(SKILLS_REF) validate "$$skill_dir"; \
	done

skill-manifest-check: skill-frontmatter-lint skill-manifest-validate

typecheck: syntax-check
	@echo "typecheck: no static type checker configured (ran syntax-check)"

spelling:
	@uv run --script scripts/typos_rollout_cli.py generate --repository . --source data/typos-oxendict-base.toml
	@git ls-files --error-unmatch typos.toml >/dev/null
	@git diff --exit-code -- typos.toml
	@uv run --script scripts/typos_rollout_cli.py check --repository .
	@$(TYPOS) --config typos.toml --force-exclude .

test:
	@$(PYTEST) $(TEST_TARGETS) -v

test-entrypoints:
	@$(PYTEST) $(ENTRYPOINT_TESTS) -v
