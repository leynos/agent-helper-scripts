"""Process-level tests for the Verus run-verus.sh reference script.

The tests exercise run-verus.sh through subprocess invocations against
tmp_path-isolated file trees. External commands (rustup, verus) are
intercepted via cmd-mox stubs to avoid toolchain requirements.
"""

from __future__ import annotations

from pathlib import Path

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

    def test_verus_bin_direct_path(self, tmp_path: Path) -> None:
        """When VERUS_BIN points to an executable file, it is used directly."""
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

        assert result.returncode == 0, (
            f"unexpected exit {result.returncode}; stderr={result.stderr!r}"
        )
        assert "[run-verus] operation=run-proof" in result.stderr, result.stderr

    def test_verus_bin_directory(self, tmp_path: Path) -> None:
        """When VERUS_BIN is a directory containing a verus binary, resolve it."""
        repo = make_repo_tree(tmp_path)

        verus_dir = tmp_path / "verus-install"
        verus_dir.mkdir()
        make_fake_verus(verus_dir / "verus")

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = run_script(
                repo / "skills" / "verus" / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(verus_dir),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0, (
            f"unexpected exit {result.returncode}; stderr={result.stderr!r}"
        )

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
