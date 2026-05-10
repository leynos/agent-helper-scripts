"""Process-level tests for the Verus run-verus.sh reference script.

The tests exercise run-verus.sh through subprocess invocations against
tmp_path-isolated file trees. External commands (rustup, verus) are
intercepted via cmd-mox stubs to avoid toolchain requirements.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cmd_mox import CmdMox

from verus_helpers import FAKE_VERSION, make_fake_verus, make_repo_tree, run_script


class TestRunVerus:
    """Tests for run-verus.sh."""

    def test_missing_version_file(self, tmp_path: Path) -> None:
        """Missing VERSION file causes non-zero exit with error."""
        repo = make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "VERSION").unlink()

        result = run_script(repo / "skills" / "verus" / "references" / "run-verus.sh", cwd=repo)

        assert result.returncode != 0, (
            f"expected non-zero exit; stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
        assert "Missing Verus version file" in result.stderr, result.stderr

    @pytest.mark.parametrize(
        "bin_value_factory, description",
        [
            (lambda d, v: v, "direct executable path"),
            (lambda d, v: d, "directory containing verus binary"),
        ],
    )
    def test_verus_bin_resolution(
        self,
        tmp_path: Path,
        bin_value_factory,
        description: str,
    ) -> None:
        """VERUS_BIN is resolved correctly whether it is a file or a directory."""
        repo = make_repo_tree(tmp_path)

        verus_dir = tmp_path / "verus-install"
        verus_dir.mkdir()
        fake_verus = verus_dir / "verus"
        make_fake_verus(fake_verus)

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        bin_value = bin_value_factory(verus_dir, fake_verus)

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(bin_value),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0, (
            f"{description}: unexpected exit {result.returncode}; stderr={result.stderr!r}"
        )
        assert "[run-verus] operation=resolve-toolchain" in result.stderr, result.stderr
        assert "[run-verus] operation=run-proof" in result.stderr, (
            f"{description}: run-proof diagnostic not emitted; stderr={result.stderr!r}"
        )

    def test_install_toolchain_diagnostic(self, tmp_path: Path) -> None:
        """resolve-toolchain and install-toolchain diagnostics emitted when toolchain absent."""
        repo = make_repo_tree(tmp_path)

        fake_verus = tmp_path / "fake-verus"
        make_fake_verus(fake_verus)

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            def _rustup_response(invocation):
                """Return rustup responses that force the install-toolchain path."""
                if invocation.args[:4] == [
                    "which",
                    "--toolchain",
                    "nightly-2025-11-05",
                    "rustc",
                ]:
                    return (
                        "",
                        "toolchain 'nightly-2025-11-05' is not installed\n",
                        1,
                    )
                if invocation.args[:3] == [
                    "toolchain",
                    "install",
                    "nightly-2025-11-05",
                ]:
                    return "", "", 0
                return "", f"unexpected rustup args: {invocation.args!r}\n", 1

            mox.stub("rustup").runs(_rustup_response)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(fake_verus),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert "[run-verus] operation=resolve-toolchain" in result.stderr, result.stderr
        assert "[run-verus] operation=install-toolchain" in result.stderr, result.stderr

    def test_diagnostic_lines_match_snapshot(
        self, tmp_path: Path, snapshot
    ) -> None:
        """Structured diagnostic lines emitted during proof run match the snapshot schema."""
        repo = make_repo_tree(tmp_path)

        fake_verus = tmp_path / "fake-verus"
        make_fake_verus(fake_verus)

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(fake_verus),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        import re

        diag_lines = [
            re.sub(
                str(tmp_path),
                "<tmp>",
                re.sub(r"elapsed=\d+s", "elapsed=Xs", line),
            )
            for line in result.stderr.splitlines()
            if line.startswith("[run-verus]")
        ]
        assert diag_lines == snapshot

    def test_proof_file_not_found(self, tmp_path: Path) -> None:
        """When the proof file does not exist, exit non-zero with error."""
        repo = make_repo_tree(tmp_path)

        fake_verus = tmp_path / "fake-verus"
        make_fake_verus(fake_verus)

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(fake_verus),
                    "VERUS_PROOF_FILE": str(tmp_path / "nonexistent.rs"),
                },
            )

        assert result.returncode != 0, (
            f"expected non-zero exit; stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
        assert "Verus proof file not found" in result.stderr, result.stderr

    def test_verus_binary_not_executable_after_install(
        self, tmp_path: Path
    ) -> None:
        """Non-executable binary after resolution causes non-zero exit."""
        repo = make_repo_tree(tmp_path)

        # Create a non-executable file where the default binary would be.
        install_dir = repo / ".verus" / FAKE_VERSION / "verus"
        install_dir.mkdir(parents=True)
        verus_bin = install_dir / "verus"
        verus_bin.write_text("not executable\n")
        verus_bin.chmod(0o644)

        result = run_script(repo / "skills" / "verus" / "references" / "run-verus.sh", cwd=repo)

        assert result.returncode != 0, (
            f"expected non-zero exit; stdout={result.stdout!r}; stderr={result.stderr!r}"
        )
        assert "Verus binary" in result.stderr or "not executable" in result.stderr, (
            result.stderr
        )

    def test_fallback_to_install(self, tmp_path: Path) -> None:
        """When no binary is resolvable, the script calls install-verus.sh."""
        repo = make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION / "verus"

        # Replace the symlinked install-verus.sh with a fake that creates a
        # working verus binary.
        fake_install = repo / "skills" / "verus" / "references" / "install-verus.sh"
        fake_install.unlink()
        fake_install.write_text(
            f'#!/bin/sh\n'
            f'mkdir -p "{install_dir}"\n'
            f'cat > "{install_dir}/verus" << \'VERUS\'\n'
            f'#!/bin/sh\n'
            f'case "$1" in\n'
            f'  --version) echo "Toolchain: nightly-2025-11-05" ;;\n'
            f'  *) echo "verified" ;;\n'
            f'esac\n'
            f'VERUS\n'
            f'chmod 755 "{install_dir}/verus"\n'
        )
        fake_install.chmod(0o755)

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0, (
            f"unexpected exit {result.returncode}; stderr={result.stderr!r}"
        )
        assert install_dir.exists(), f"install directory not found at {install_dir}"
