SHELL := /usr/bin/env bash

SHELL_SCRIPTS := install-hooks bin/install-hook-cmd.sh
PYTHON_SCRIPTS := hooks/post-turn-quality-stop-hook.py

.PHONY: check-fmt lint typecheck test

check-fmt:
	@echo "check-fmt: no formatter configured"

lint:
	@bash -n $(SHELL_SCRIPTS)
	@python3 -m py_compile $(PYTHON_SCRIPTS)

typecheck:
	@python3 -m py_compile $(PYTHON_SCRIPTS)

test:
	@echo "test: no tests configured"
