#!/usr/bin/env python3
"""
Hexagonal architecture constraint validator.

Checks for common dependency rule violations by analysing imports.
Run from project root: python scripts/validate_architecture.py

Expects standard layout:
  src/domain/     - Domain layer (no infrastructure imports)
  src/application/ - Application layer (no adapter imports)
  src/adapters/   - Adapter layer
"""

import ast
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator

# Infrastructure modules that should never appear in domain
INFRASTRUCTURE_MODULES = frozenset({
    # ORMs
    "sqlalchemy", "peewee", "tortoise", "django",
    # Web frameworks
    "flask", "fastapi", "starlette", "django", "aiohttp", "sanic",
    # HTTP clients
    "requests", "httpx", "aiohttp", "urllib3",
    # Message queues
    "pika", "aiokafka", "celery", "redis", "boto3",
    # Databases
    "psycopg2", "asyncpg", "pymongo", "motor",
})

# Application layer should not import from adapters
ADAPTER_IMPORT_PATTERNS = frozenset({
    "adapters",
})


@dataclass
class Violation:
    file: Path
    line: int
    module: str
    layer: str
    message: str


def extract_imports(
    source: str,
    source_name: str = "<unknown>",
) -> Iterator[tuple[int, str]]:
    """Yield (line_number, module_name) for all imports in source.

    Args:
        source: Python source text to parse.
        source_name: Human-readable label for diagnostic messages
            (typically a file path).
    """
    try:
        tree = ast.parse(source, filename=source_name)
    except SyntaxError as e:
        print(
            f"Warning: skipped {source_name!r} due to SyntaxError: {e}",
            file=sys.stderr,
        )
        return
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                yield node.lineno, node.module.split(".")[0]


def check_domain_layer(domain_path: Path) -> Iterator[Violation]:
    """Check domain layer for infrastructure imports."""
    for py_file in domain_path.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        for line, module in extract_imports(source, source_name=str(py_file)):
            if module in INFRASTRUCTURE_MODULES:
                yield Violation(
                    file=py_file,
                    line=line,
                    module=module,
                    layer="domain",
                    message=f"Domain imports infrastructure module '{module}'",
                )
            if module in ADAPTER_IMPORT_PATTERNS:
                yield Violation(
                    file=py_file,
                    line=line,
                    module=module,
                    layer="domain",
                    message=f"Domain imports from adapters",
                )


def check_application_layer(app_path: Path) -> Iterator[Violation]:
    """Check application layer for adapter imports."""
    for py_file in app_path.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        for line, module in extract_imports(source, source_name=str(py_file)):
            if module in ADAPTER_IMPORT_PATTERNS:
                yield Violation(
                    file=py_file,
                    line=line,
                    module=module,
                    layer="application",
                    message=f"Application layer imports from adapters",
                )


def check_domain_tests(tests_path: Path) -> Iterator[Violation]:
    """Check domain tests don't use infrastructure."""
    domain_tests = tests_path / "domain"
    if not domain_tests.exists():
        return
    
    for py_file in domain_tests.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        for line, module in extract_imports(source, source_name=str(py_file)):
            if module in INFRASTRUCTURE_MODULES:
                yield Violation(
                    file=py_file,
                    line=line,
                    module=module,
                    layer="domain-tests",
                    message=f"Domain test imports infrastructure '{module}' (tests should use fakes)",
                )


def main() -> int:
    """Validate hexagonal architecture boundaries from the CLI.

    Returns
    -------
    int
        0 when no violations are found, 1 when at least one violation is
        detected or the ``src/`` directory is missing.
    """
    src_path = Path("src")
    tests_path = Path("tests")
    
    if not src_path.exists():
        print("Error: src/ directory not found. Run from project root.")
        return 1
    
    violations: list[Violation] = []
    
    domain_path = src_path / "domain"
    if domain_path.exists():
        violations.extend(check_domain_layer(domain_path))
    
    app_path = src_path / "application"
    if app_path.exists():
        violations.extend(check_application_layer(app_path))
    
    if tests_path.exists():
        violations.extend(check_domain_tests(tests_path))
    
    if violations:
        print(f"Found {len(violations)} architecture violation(s):\n")
        for v in violations:
            print(f"  {v.file}:{v.line}")
            print(f"    [{v.layer}] {v.message}\n")
        return 1
    
    print("✓ No architecture violations found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
