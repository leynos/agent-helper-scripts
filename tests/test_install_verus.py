"""Process-level tests for the Verus install-verus.sh reference script.

The tests exercise install-verus.sh through subprocess invocations against
tmp_path-isolated file trees. External commands (curl, sha256sum, unzip) are
intercepted via fake scripts on PATH to avoid network access and toolchain
requirements.
"""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from pathlib import Path

from verus_helpers import FAKE_TARGET, FAKE_VERSION, make_repo_tree, run_script


class TestInstallVerus:
    """Tests for install-verus.sh."""

    def test_idempotent_when_already_installed(self, tmp_path: Path) -> None:
        """When the Verus binary already exists the script exits 0 immediately."""
        repo = make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION / "verus"
        install_dir.mkdir(parents=True)
        verus_bin = install_dir / "verus"
        verus_bin.write_text(f"#!/bin/sh\necho verus {FAKE_VERSION}\n")
        verus_bin.chmod(0o755)

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode == 0
        assert "already installed" in result.stdout

    def test_missing_version_file(self, tmp_path: Path) -> None:
        """Missing VERSION file causes immediate non-zero exit."""
        repo = make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "VERSION").unlink()

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing Verus version file" in result.stderr

    def test_missing_sha256sums_file(self, tmp_path: Path) -> None:
        """Missing SHA256SUMS file causes immediate non-zero exit."""
        repo = make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "SHA256SUMS").unlink()

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing Verus checksum file" in result.stderr

    def test_missing_sha256sums_entry(self, tmp_path: Path) -> None:
        """SHA256SUMS with no matching entry causes non-zero exit."""
        repo = make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "SHA256SUMS").write_text(
            "deadbeef  verus-other-version.zip\n"
        )

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0
        assert "Missing SHA-256" in result.stderr

    def test_checksum_mismatch(self, tmp_path: Path) -> None:
        """Checksum mismatch causes non-zero exit with error to stderr."""
        repo = make_repo_tree(tmp_path)

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

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
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
        repo = make_repo_tree(tmp_path)

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

        result = run_script(
            repo / "skills" / "verus" / "references" / "install-verus.sh",
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}:{os.environ['PATH']}",
            },
        )

        assert result.returncode == 0, result.stderr
        assert (install_dir / "verus" / "verus").exists()
        assert (install_dir / "verus" / "verus").stat().st_mode & stat.S_IXUSR
