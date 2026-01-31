SHELL := /usr/bin/env bash

SHELL_SCRIPTS := install-hooks bin/install-hook-cmd.sh
PYTHON_SCRIPTS := hooks/post-turn-quality-stop-hook.py

.PHONY: all clean check-fmt lint typecheck syntax-check test

all: check-fmt lint typecheck test

clean:
	@echo "clean: nothing to clean"

check-fmt:
	@echo "check-fmt: no formatter configured"

syntax-check:
	@python3 -m py_compile $(PYTHON_SCRIPTS)

lint: syntax-check
	@bash -n $(SHELL_SCRIPTS)

typecheck: syntax-check
	@echo "typecheck: no static type checker configured (ran syntax-check)"

test:
	@echo "test: no tests configured"
