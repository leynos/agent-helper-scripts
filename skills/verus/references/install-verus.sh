#!/usr/bin/env bash
# Reference: Verus installation script from chutoro
#
# This script reads a pinned Verus version and checksum from version files,
# downloads the matching release asset, verifies its SHA-256 checksum, and
# extracts it to an install directory. It is idempotent: if the correct
# version is already installed, it exits immediately.
#
# Environment variables:
#   VERUS_INSTALL_DIR  Override the installation location.
#   VERUS_TARGET       Select a different release asset (default: x86-linux).
#
# Required files (relative to repository root):
#   tools/verus/VERSION     Pinned Verus release identifier.
#   tools/verus/SHA256SUMS  Expected checksums for release assets.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
VERSION_FILE="${ROOT_DIR}/tools/verus/VERSION"
CHECKSUM_FILE="${ROOT_DIR}/tools/verus/SHA256SUMS"

if [[ ! -f "${VERSION_FILE}" ]]; then
  echo "Missing Verus version file: ${VERSION_FILE}" >&2
  exit 1
fi
if [[ ! -f "${CHECKSUM_FILE}" ]]; then
  echo "Missing Verus checksum file: ${CHECKSUM_FILE}" >&2
  exit 1
fi

VERUS_VERSION="$(cat "${VERSION_FILE}")"
VERUS_TARGET="${VERUS_TARGET:-x86-linux}"
INSTALL_DIR="${VERUS_INSTALL_DIR:-${ROOT_DIR}/.verus/${VERUS_VERSION}}"
ARCHIVE="verus-${VERUS_VERSION}-${VERUS_TARGET}.zip"
URL="https://github.com/verus-lang/verus/releases/download/release/${VERUS_VERSION}/${ARCHIVE}"
EXPECTED_SHA="$(
  awk -v archive="${ARCHIVE}" '$2 == archive {print $1; exit}' "${CHECKSUM_FILE}"
)"
if [[ -z "${EXPECTED_SHA}" ]]; then
  echo "Missing SHA-256 for ${ARCHIVE} in ${CHECKSUM_FILE}" >&2
  exit 1
fi

if [[ -x "${INSTALL_DIR}/verus/verus" ]]; then
  echo "Verus ${VERUS_VERSION} already installed at ${INSTALL_DIR}/verus"
  exit 0
fi

mkdir -p "${INSTALL_DIR}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

curl -sSfL "${URL}" -o "${TMP_DIR}/${ARCHIVE}"

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "${TMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA="$(shasum -a 256 "${TMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
else
  echo "Missing SHA-256 tool (sha256sum or shasum)." >&2
  exit 1
fi

if [[ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]]; then
  echo "SHA-256 mismatch for ${ARCHIVE}." >&2
  echo "Expected: ${EXPECTED_SHA}" >&2
  echo "Actual:   ${ACTUAL_SHA}" >&2
  exit 1
fi

unzip -q "${TMP_DIR}/${ARCHIVE}" -d "${INSTALL_DIR}"

EXTRACTED_DIR="${INSTALL_DIR}/verus-${VERUS_TARGET}"
if [[ ! -d "${EXTRACTED_DIR}" ]]; then
  EXTRACTED_DIR="$(find "${INSTALL_DIR}" -maxdepth 1 -type d -name 'verus-*' | head -n 1)"
fi

if [[ -z "${EXTRACTED_DIR}" || ! -d "${EXTRACTED_DIR}" ]]; then
  echo "Unable to locate extracted Verus directory under ${INSTALL_DIR}" >&2
  exit 1
fi

BACKUP="${INSTALL_DIR}/verus.old.$$"
if [[ -e "${INSTALL_DIR}/verus" ]]; then
  mv "${INSTALL_DIR}/verus" "${BACKUP}"
fi

if ! mv "${EXTRACTED_DIR}" "${INSTALL_DIR}/verus"; then
  echo "Failed to move extracted directory into place." >&2
  if [[ -d "${BACKUP}" ]]; then
    mv "${BACKUP}" "${INSTALL_DIR}/verus"
    echo "Restored previous installation." >&2
  fi
  exit 1
fi

rm -rf "${BACKUP}"

cat <<EOM
Installed Verus ${VERUS_VERSION} in ${INSTALL_DIR}/verus
Export VERUS_BIN=${INSTALL_DIR}/verus/verus
EOM
