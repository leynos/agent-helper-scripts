"""Process-level tests for the Verus reference helper scripts.

The tests exercise install-verus.sh and run-verus.sh through subprocess
invocations against tmp_path-isolated file trees. External commands (curl,
sha256sum, unzip, rustup, verus) are intercepted via cmd-mox to avoid
network access and toolchain requirements.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import zipfile
from pathlib import Path

from cmd_mox import CmdMox, skip_if_unsupported


skip_if_unsupported()

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "skills" / "verus" / "references" / "install-verus.sh"
RUN_SCRIPT = REPO_ROOT / "skills" / "verus" / "references" / "run-verus.sh"

FAKE_VERSION = "0.2026.01.30.test123"
FAKE_TARGET = "x86-linux"


def _make_repo_tree(tmp_path: Path) -> Path:
    """Build a minimal fake repository tree with tools/verus metadata.

    Returns the repo directory. The scripts are symlinked into
    repo/references/ so that BASH_SOURCE[0]-derived ROOT_DIR resolves
    to repo.
    """
    repo = tmp_path / "repo"
    tools = repo / "tools" / "verus"
    tools.mkdir(parents=True)
    refs = repo / "references"
    refs.mkdir()

    (tools / "VERSION").write_text(FAKE_VERSION)

    archive_name = f"verus-{FAKE_VERSION}-{FAKE_TARGET}.zip"
    fake_sha = "a" * 64
    (tools / "SHA256SUMS").write_text(f"{fake_sha}  {archive_name}\n")

    # Symlink the real scripts into the fake repo references/ directory.
    (refs / "install-verus.sh").symlink_to(INSTALL_SCRIPT)
    (refs / "run-verus.sh").symlink_to(RUN_SCRIPT)

    return repo


def _run_script(
    script: Path,
    *,
    cwd: Path,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a bash script with optional environment overrides."""
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)

    return subprocess.run(
        ["bash", str(script)],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _make_fake_verus(path: Path) -> None:
    """Write a fake verus binary that reports a toolchain on --version."""
    path.write_text(
        '#!/bin/sh\n'
        'case "$1" in\n'
        '  --version) echo "Toolchain: nightly-2025-11-05" ;;\n'
        '  *) echo "verified" ;;\n'
        'esac\n'
    )
    path.chmod(0o755)


# ============================================================================
# install-verus.sh tests
# ============================================================================


class TestInstallVerus:
    """Tests for install-verus.sh."""

    def test_idempotent_when_already_installed(self, tmp_path: Path) -> None:
        """When the Verus binary already exists the script exits 0 immediately."""
        repo = _make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION / "verus"
        install_dir.mkdir(parents=True)
        verus_bin = install_dir / "verus"
        verus_bin.write_text("#!/bin/sh\necho fake\n")
        verus_bin.chmod(0o755)

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode == 0
        assert "already installed" in result.stdout

    def test_missing_version_file(self, tmp_path: Path) -> None:
        """Missing VERSION file causes immediate non-zero exit."""
        repo = _make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "VERSION").unlink()

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing Verus version file" in result.stderr

    def test_missing_sha256sums_file(self, tmp_path: Path) -> None:
        """Missing SHA256SUMS file causes immediate non-zero exit."""
        repo = _make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "SHA256SUMS").unlink()

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing Verus checksum file" in result.stderr

    def test_missing_sha256sums_entry(self, tmp_path: Path) -> None:
        """SHA256SUMS with no matching entry causes non-zero exit."""
        repo = _make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "SHA256SUMS").write_text(
            "deadbeef  verus-other-version.zip\n"
        )

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing SHA-256" in result.stderr

    def test_checksum_mismatch(self, tmp_path: Path) -> None:
        """Checksum mismatch causes non-zero exit with error to stderr."""
        repo = _make_repo_tree(tmp_path)

        archive_name = f"verus-{FAKE_VERSION}-{FAKE_TARGET}.zip"
        wrong_sha = "b" * 64
        (repo / "tools" / "verus" / "SHA256SUMS").write_text(
            f"{wrong_sha}  {archive_name}\n"
        )

        # Build a real zip so curl has something to download.
        zip_path = tmp_path / archive_name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"verus-{FAKE_TARGET}/verus", "#!/bin/sh\necho fake\n")

        # Provide a fake curl that copies the archive.
        fake_bin_dir = tmp_path / "fakebin"
        fake_bin_dir.mkdir()
        fake_curl = fake_bin_dir / "curl"
        fake_curl.write_text(
            f'#!/bin/sh\n'
            f'while [ "$#" -gt 0 ]; do\n'
            f'  case "$1" in\n'
            f'    -o) shift; cp "{zip_path}" "$1"; exit 0 ;;\n'
            f'    *) shift ;;\n'
            f'  esac\n'
            f'done\n'
            f'exit 1\n'
        )
        fake_curl.chmod(0o755)

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
            },
        )

        assert result.returncode != 0
        assert "SHA-256 mismatch" in result.stderr

    def test_successful_install(self, tmp_path: Path) -> None:
        """Successful install creates the Verus binary at the expected path."""
        repo = _make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION
        archive_name = f"verus-{FAKE_VERSION}-{FAKE_TARGET}.zip"

        # Build a real ZIP archive containing a verus binary.
        zip_dir = tmp_path / "zip_build"
        zip_dir.mkdir()
        verus_tree = zip_dir / f"verus-{FAKE_TARGET}"
        verus_tree.mkdir()
        verus_bin = verus_tree / "verus"
        verus_bin.write_text("#!/bin/sh\necho verus-fake\n")
        verus_bin.chmod(0o755)

        zip_path = tmp_path / archive_name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(verus_bin, f"verus-{FAKE_TARGET}/verus")

        # Compute the real SHA-256 of the archive.
        sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
        (repo / "tools" / "verus" / "SHA256SUMS").write_text(
            f"{sha}  {archive_name}\n"
        )

        # Override curl to copy our pre-built archive.
        fake_bin_dir = tmp_path / "fakebin"
        fake_bin_dir.mkdir()
        fake_curl = fake_bin_dir / "curl"
        fake_curl.write_text(
            f'#!/bin/sh\n'
            f'while [ "$#" -gt 0 ]; do\n'
            f'  case "$1" in\n'
            f'    -o) shift; cp "{zip_path}" "$1"; exit 0 ;;\n'
            f'    *) shift ;;\n'
            f'  esac\n'
            f'done\n'
            f'exit 1\n'
        )
        fake_curl.chmod(0o755)

        result = _run_script(
            repo / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
            },
        )

        assert result.returncode == 0, result.stderr
        assert (install_dir / "verus" / "verus").exists()
        assert (install_dir / "verus" / "verus").stat().st_mode & stat.S_IXUSR


# ============================================================================
# run-verus.sh tests
# ============================================================================


class TestRunVerus:
    """Tests for run-verus.sh."""

    def test_missing_version_file(self, tmp_path: Path) -> None:
        """Missing VERSION file causes non-zero exit with error."""
        repo = _make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "VERSION").unlink()

        result = _run_script(repo / "references" / "run-verus.sh", cwd=repo)

        assert result.returncode != 0
        assert "Missing Verus version file" in result.stderr

    def test_verus_bin_direct_path(self, tmp_path: Path) -> None:
        """When VERUS_BIN points to an executable file, it is used directly."""
        repo = _make_repo_tree(tmp_path)

        fake_verus = tmp_path / "fake-verus"
        _make_fake_verus(fake_verus)

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = _run_script(
                repo / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(fake_verus),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0

    def test_verus_bin_directory(self, tmp_path: Path) -> None:
        """When VERUS_BIN is a directory containing a verus binary, resolve it."""
        repo = _make_repo_tree(tmp_path)

        verus_dir = tmp_path / "verus-install"
        verus_dir.mkdir()
        _make_fake_verus(verus_dir / "verus")

        proof_file = tmp_path / "proof.rs"
        proof_file.write_text("fn main() {}\n")

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = _run_script(
                repo / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(verus_dir),
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0

    def test_proof_file_not_found(self, tmp_path: Path) -> None:
        """When the proof file does not exist, exit non-zero with error."""
        repo = _make_repo_tree(tmp_path)

        fake_verus = tmp_path / "fake-verus"
        _make_fake_verus(fake_verus)

        with CmdMox() as mox:
            mox.stub("rustup").returns(exit_code=0)
            mox.replay()

            result = _run_script(
                repo / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_BIN": str(fake_verus),
                    "VERUS_PROOF_FILE": str(tmp_path / "nonexistent.rs"),
                },
            )

        assert result.returncode != 0
        assert "Verus proof file not found" in result.stderr

    def test_verus_binary_not_executable_after_install(
        self, tmp_path: Path
    ) -> None:
        """Non-executable binary after resolution causes non-zero exit."""
        repo = _make_repo_tree(tmp_path)

        # Create a non-executable file where the default binary would be.
        install_dir = repo / ".verus" / FAKE_VERSION / "verus"
        install_dir.mkdir(parents=True)
        verus_bin = install_dir / "verus"
        verus_bin.write_text("not executable\n")
        verus_bin.chmod(0o644)

        result = _run_script(repo / "references" / "run-verus.sh", cwd=repo)

        assert result.returncode != 0
        assert "Verus binary" in result.stderr or "not executable" in result.stderr

    def test_fallback_to_install(self, tmp_path: Path) -> None:
        """When no binary is resolvable, the script calls install-verus.sh."""
        repo = _make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION / "verus"

        # Replace the symlinked install-verus.sh with a fake that creates a
        # working verus binary.
        fake_install = repo / "references" / "install-verus.sh"
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

            result = _run_script(
                repo / "references" / "run-verus.sh",
                cwd=repo,
                env_overrides={
                    "VERUS_PROOF_FILE": str(proof_file),
                },
            )

        assert result.returncode == 0
        assert install_dir.exists()
