"""Find, verify and install the pinned FizzBee release.

The suite pins one checker release by archive digest and by the digest of
every file it unpacks to. This module is the checker's distribution: where
the release lives under a home directory, whether the files there are the
pinned bytes, and fetching and unpacking the archive when they are not. Suite
execution is ``model_check``'s concern; it only asks for a verified
launcher.

``checker_launcher`` is a path computation. ``verify_checker`` reads and
hashes every pinned file, so the cost of verification is visible at each call
site. The network is used only through the injected ``Fetcher``.
"""

from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
import shutil
import tarfile

from model_check_suite import Checker, ModelCheckError

#: Fetches ``url`` to ``destination``.
Fetcher = Callable[[str, Path], None]


class CheckerAbsentError(ModelCheckError):
    """Report that the pinned release is missing or is not the pinned bytes.

    This is the one checker failure installing repairs. A pinned file that
    exists and cannot be read is a plain ``ModelCheckError`` instead, so an
    install never downloads over a release it could not inspect.
    """


def remove_tree(directory: Path) -> None:
    """Delete a directory tree that may be absent, or say why it cannot be.

    Raises
    ------
    ModelCheckError
        Raised, naming the directory, when it exists and cannot be removed.
    """
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        return
    except OSError as error:
        raise ModelCheckError(f"cannot remove {directory}: {error}") from error


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file, read in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checker_root(home: Path, checker: Checker) -> Path:
    """Return the directory the pinned release unpacks to under ``home``.

    A relative home would be resolved again from each child's working
    directory, so it is resolved once, from the caller's. Nothing is read
    or verified.
    """
    return home.resolve() / checker.root


def checker_launcher(home: Path, checker: Checker) -> Path:
    """Return where the release's ``fizz`` launcher is, without verifying it."""
    return checker_root(home, checker) / "fizz"


def _pinned_digest(candidate: Path) -> str:
    """Return a pinned file's digest, naming the file when it cannot be read."""
    try:
        return _sha256(candidate)
    except OSError as error:
        raise ModelCheckError(f"cannot read the pinned checker file {candidate}: {error}") from error


def verify_checker(home: Path, checker: Checker) -> Path:
    """Hash every pinned file under ``home`` and return the verified launcher.

    Parameters
    ----------
    home : Path
        The directory the release was unpacked into.
    checker : Checker
        The pin the unpacked files must match.

    Returns
    -------
    Path
        The ``fizz`` launcher inside the unpacked release.

    Raises
    ------
    CheckerAbsentError
        Raised when a pinned file is absent, which is a missing checker, or
        has another digest, which is an incompatible one.
    ModelCheckError
        Raised, naming the file, when a pinned file cannot be read.
    """
    root = checker_root(home, checker)
    for name, expected in checker.files.items():
        candidate = root / name
        if not candidate.is_file():
            raise CheckerAbsentError(
                f"FizzBee {checker.version} is not installed: {candidate} is"
                " missing. Run `make fizzbee` to fetch the pinned release."
            )
        actual = _pinned_digest(candidate)
        if actual != expected:
            raise CheckerAbsentError(
                f"FizzBee at {root} is not the pinned {checker.version}:"
                f" {name} has SHA-256 {actual}, expected {expected}."
                " Run `make fizzbee` to fetch the pinned release."
            )
    return checker_launcher(home, checker)


def _download_and_unpack(home: Path, checker: Checker, fetch: Fetcher, archive: Path) -> None:
    """Fetch the archive, check its digest, and unpack it over the release.

    Raises
    ------
    ModelCheckError
        Raised when the download, the digest check or the unpacking fails.
    """
    try:
        fetch(checker.url, archive)
        actual = _sha256(archive)
        if actual != checker.archive_sha256:
            raise ModelCheckError(
                f"downloaded FizzBee archive has SHA-256 {actual}, expected"
                f" {checker.archive_sha256}; nothing was unpacked"
            )
        remove_tree(home / checker.root)
        with tarfile.open(archive) as bundle:
            bundle.extractall(home, filter="data")
    except (OSError, tarfile.TarError) as error:
        raise ModelCheckError(f"cannot install FizzBee: {error}") from error


def _discard(archive: Path) -> None:
    """Remove the downloaded archive, naming it when it cannot be removed."""
    try:
        archive.unlink(missing_ok=True)
    except OSError as error:
        raise ModelCheckError(f"cannot remove the downloaded archive {archive}: {error}") from error


def install_checker(home: Path, checker: Checker, fetch: Fetcher) -> Path:
    """Fetch, verify and unpack the pinned release unless it is present.

    Parameters
    ----------
    home : Path
        The directory to unpack into. It is created when absent.
    checker : Checker
        The release to install and the digests it must have.
    fetch : Fetcher
        Downloads the archive. This is the only step that uses the network.

    Returns
    -------
    Path
        The verified ``fizz`` launcher.

    Raises
    ------
    ModelCheckError
        Raised, naming the path, when an installed pinned file cannot be
        read, which installing would not repair; when ``home`` cannot be
        created; when the downloaded archive has another digest or cannot be
        unpacked; when the unpacked files do not match the pin; or when the
        downloaded archive cannot be removed afterwards. A failed install
        reports its own error, with any failure to remove the archive added
        as a note rather than replacing it.
    """
    home = home.resolve()
    try:
        return verify_checker(home, checker)
    except CheckerAbsentError:
        pass
    try:
        home.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ModelCheckError(f"cannot create the checker home {home}: {error}") from error
    archive = home / f"{checker.root}.tar.gz.partial"
    try:
        _download_and_unpack(home, checker, fetch, archive)
    except BaseException as failure:
        # The install's own error is the one to report; a failure to remove
        # the partial archive is added to it, never raised in its place.
        try:
            _discard(archive)
        except ModelCheckError as cleanup:
            failure.add_note(str(cleanup))
        raise
    _discard(archive)
    return verify_checker(home, checker)
