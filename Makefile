SHELL := /usr/bin/env
.SHELLFLAGS := bash -c

SHELL_SCRIPTS := \
	add-repositories \
	apt-update-if-stale \
	bootstrap-common \
	get-ai-tooling \
	get-github-tooling \
	get-markdown-tooling \
	get-open-tofu-tooling \
	get-postgresql \
	get-python-tooling \
	get-rust-tooling \
	get-typescript-tooling \
	install-hooks \
	install-required-apt-packages \
	install-skills \
	install-sub-agents \
	markdownlint \
	mdformat-all \
	notdeadyet \
	python-setup \
	rust-entrypoint \
	rust-entrypoint-home \
	rust-entrypoint-system \
	rust-setup \
	bin/install-hook-cmd.sh
HOME_PHASE_SCRIPTS := \
	rust-entrypoint-home \
	get-rust-tooling \
	get-markdown-tooling \
	get-github-tooling \
	get-python-tooling \
	install-skills \
	install-hooks \
	install-sub-agents
PYTHON_SCRIPTS := \
	hooks/post-turn-quality-stop-hook.py \
	hooks/test_post_turn_quality_stop_hook.py \
	tests/conftest.py \
	tests/test_rust_entrypoints.py
PYTEST := uv run --with pytest --with cmd-mox --with cuprum python -m pytest

.PHONY: all clean check-fmt lint typecheck syntax-check shell-syntax-check check-home-phase-boundary test

all: check-fmt lint typecheck test

clean:
	@echo "clean: nothing to clean"

check-fmt:
	@echo "check-fmt: no formatter configured"

syntax-check:
	@python3 -m py_compile $(PYTHON_SCRIPTS)

shell-syntax-check:
	@bash -n $(SHELL_SCRIPTS)

check-home-phase-boundary:
	@! grep -R --line-number -E '\bapt-get\b|\bapt-update-if-stale\b|\bsudo\b|/etc/apt|/usr/bin/ld|update-ca-certificates|/var/lib/apt' $(HOME_PHASE_SCRIPTS)

lint: syntax-check shell-syntax-check check-home-phase-boundary

typecheck: syntax-check
	@echo "typecheck: no static type checker configured (ran syntax-check)"

test:
	@$(PYTEST) hooks/test_post_turn_quality_stop_hook.py tests/test_rust_entrypoints.py -v
