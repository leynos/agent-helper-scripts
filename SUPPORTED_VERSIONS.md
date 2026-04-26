# Supported Versions

## Python

The repository test harness is tested with Python 3.13 in CI. Python is used
for pytest-based validation, cmd-mox, cuprum, and repository quality hooks; the
shell bootstrap entrypoints remain Bash scripts and do not require Python for
the phase dispatcher itself.

Use Python 3.13 when running the full `make ci` gate locally to match the
GitHub Actions environment. Other Python versions may work, but they are not
part of the current CI policy until the workflow adds an explicit version
matrix.
