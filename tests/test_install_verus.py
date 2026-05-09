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

import pytest

from verus_helpers import FAKE_TARGET, FAKE_VERSION, make_repo_tree, run_script

INSTALL_SCRIPT = "skills" / Path("verus") / "references" / "install-verus.sh"


def _make_fake_curl(tmp_path: Path, zip_path: Path) -> Path:
    """Create a fake curl that copies a pre-built archive."""
    fake_bin_dir = tmp_path / "fakebin"
    fake_bin_dir.mkdir(exist_ok=True)
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
    return fake_bin_dir


def _make_valid_archive(tmp_path: Path, repo: Path) -> Path:
    """Build a valid ZIP archive with correct checksum and return the fake bin dir."""
    archive_name = f"verus-{FAKE_VERSION}-{FAKE_TARGET}.zip"

    zip_dir = tmp_path / "zip_build"
    zip_dir.mkdir(exist_ok=True)
    verus_tree = zip_dir / f"verus-{FAKE_TARGET}"
    verus_tree.mkdir(exist_ok=True)
    verus_bin = verus_tree / "verus"
    verus_bin.write_text("#!/bin/sh\necho verus-fake\n")
    verus_bin.chmod(0o755)

    zip_path = tmp_path / archive_name
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(verus_bin, f"verus-{FAKE_TARGET}/verus")

    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (repo / "tools" / "verus" / "SHA256SUMS").write_text(
        f"{sha}  {archive_name}\n"
    )

    return _make_fake_curl(tmp_path, zip_path)


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
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode == 0, result.stderr
        assert "already installed" in result.stdout, result.stdout

    def test_reinstall_on_mismatched_version(self, tmp_path: Path) -> None:
        """When the existing binary reports a different version, reinstall."""
        repo = make_repo_tree(tmp_path)

        install_dir = repo / ".verus" / FAKE_VERSION
        verus_dir = install_dir / "verus"
        verus_dir.mkdir(parents=True)
        verus_bin = verus_dir / "verus"
        verus_bin.write_text("#!/bin/sh\necho verus 0.0.0.wrong\n")
        verus_bin.chmod(0o755)

        fake_bin_dir = _make_valid_archive(tmp_path, repo)

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        assert result.returncode == 0, result.stderr
        assert "does not match" in result.stderr, result.stderr
        assert "already installed" not in result.stdout, result.stdout
        installed_bin = install_dir / "verus" / "verus"
        assert installed_bin.exists(), f"binary not found at {installed_bin}"

    @pytest.mark.parametrize(
        ("filename", "expected_error"),
        [
            ("tools/verus/VERSION", "Missing Verus version file"),
            ("tools/verus/SHA256SUMS", "Missing Verus checksum file"),
        ],
    )
    def test_missing_required_file(
        self, tmp_path: Path, filename: str, expected_error: str
    ) -> None:
        """Missing required metadata file causes immediate non-zero exit."""
        repo = make_repo_tree(tmp_path)
        (repo / filename).unlink()

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0, result.stdout
        assert expected_error in result.stderr, result.stderr

    def test_missing_sha256sums_entry(self, tmp_path: Path) -> None:
        """SHA256SUMS with no matching entry causes non-zero exit."""
        repo = make_repo_tree(tmp_path)
        (repo / "tools" / "verus" / "SHA256SUMS").write_text(
            "deadbeef  verus-other-version.zip\n"
        )

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={"VERUS_TARGET": FAKE_TARGET},
        )

        assert result.returncode != 0, result.stdout
        assert "Missing SHA-256" in result.stderr, result.stderr

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

        fake_bin_dir = _make_fake_curl(tmp_path, zip_path)

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        assert result.returncode != 0, result.stdout
        assert "SHA-256 mismatch" in result.stderr, result.stderr

    def test_failed_replacement_rolls_back(self, tmp_path: Path) -> None:
        """When mv fails to place the extracted directory, the backup is restored."""
        repo = make_repo_tree(tmp_path)
        install_dir = repo / ".verus" / FAKE_VERSION

        # Pre-existing installation that should be restored on failure.
        verus_dir = install_dir / "verus"
        verus_dir.mkdir(parents=True)
        old_bin = verus_dir / "verus"
        old_bin.write_text("#!/bin/sh\necho old-verus\n")
        old_bin.chmod(0o755)
        sentinel = verus_dir / "sentinel"
        sentinel.write_text("original\n")

        fake_bin_dir = _make_valid_archive(tmp_path, repo)

        # Fake mv that fails once when placing the extracted dir into the
        # install target (destination ends with /verus but not /verus.old),
        # then delegates to real mv for subsequent calls (including restore).
        real_mv = "/bin/mv"
        flag_file = tmp_path / "mv_failed_once"
        fake_mv = fake_bin_dir / "mv"
        fake_mv.write_text(
            f'#!/bin/sh\n'
            f'last="$(eval echo \\${{$#}})"\n'
            f'case "$last" in\n'
            f'  */verus.old.*) exec {real_mv} "$@" ;;\n'
            f'  */verus)\n'
            f'    if [ ! -f "{flag_file}" ]; then\n'
            f'      touch "{flag_file}"\n'
            f'      exit 1\n'
            f'    fi\n'
            f'    ;;\n'
            f'esac\n'
            f'exec {real_mv} "$@"\n'
        )
        fake_mv.chmod(0o755)

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        assert result.returncode != 0, result.stderr
        assert "Failed to move" in result.stderr, result.stderr
        assert "Restored previous installation" in result.stderr, result.stderr
        restored_sentinel = install_dir / "verus" / "sentinel"
        assert restored_sentinel.exists(), "backup was not restored"
        assert restored_sentinel.read_text() == "original\n"

    def test_successful_install(self, tmp_path: Path) -> None:
        """Successful install creates the Verus binary at the expected path."""
        repo = make_repo_tree(tmp_path)
        install_dir = repo / ".verus" / FAKE_VERSION

        fake_bin_dir = _make_valid_archive(tmp_path, repo)

        result = run_script(
            repo / INSTALL_SCRIPT,
            cwd=repo,
            env_overrides={
                "VERUS_TARGET": FAKE_TARGET,
                "PATH": f"{fake_bin_dir}{os.pathsep}{os.environ['PATH']}",
            },
        )

        assert result.returncode == 0, result.stderr
        assert (install_dir / "verus" / "verus").exists()
        assert (install_dir / "verus" / "verus").stat().st_mode & stat.S_IXUSR
