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
  if "${INSTALL_DIR}/verus/verus" --version 2>&1 | grep -Fq "${VERUS_VERSION}"; then
    echo "Verus ${VERUS_VERSION} already installed at ${INSTALL_DIR}/verus"
    exit 0
  fi
  echo "Existing Verus installation does not match ${VERUS_VERSION}; reinstalling." >&2
fi

mkdir -p "${INSTALL_DIR}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

echo "[install-verus] operation=download url=\"${URL}\" target=\"${ARCHIVE}\"" >&2
_ts=$SECONDS
_dl_status=0
curl -sSfL --connect-timeout 30 --max-time 300 "${URL}" -o "${TMP_DIR}/${ARCHIVE}" || _dl_status=$?
echo "[install-verus] operation=download elapsed=$((SECONDS - _ts))s status=${_dl_status}" >&2
if [[ "${_dl_status}" -ne 0 ]]; then
  exit "${_dl_status}"
fi

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_SHA="$(sha256sum "${TMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  ACTUAL_SHA="$(shasum -a 256 "${TMP_DIR}/${ARCHIVE}" | awk '{print $1}')"
else
  echo "Missing SHA-256 tool (sha256sum or shasum)." >&2
  exit 1
fi

if [[ "${ACTUAL_SHA}" != "${EXPECTED_SHA}" ]]; then
  echo "[install-verus] operation=checksum status=mismatch" >&2
  echo "SHA-256 mismatch for ${ARCHIVE}." >&2
  echo "Expected: ${EXPECTED_SHA}" >&2
  echo "Actual:   ${ACTUAL_SHA}" >&2
  exit 1
fi
echo "[install-verus] operation=checksum status=ok" >&2

EXTRACT_ROOT="${TMP_DIR}/extract"
mkdir -p "${EXTRACT_ROOT}"
unzip -q "${TMP_DIR}/${ARCHIVE}" -d "${EXTRACT_ROOT}"

EXTRACTED_DIR="${EXTRACT_ROOT}/verus-${VERUS_TARGET}"
if [[ ! -d "${EXTRACTED_DIR}" ]]; then
  EXTRACTED_DIR="$(find "${EXTRACT_ROOT}" -maxdepth 1 -type d -name 'verus-*' | head -n 1)"
fi

if [[ -z "${EXTRACTED_DIR}" || ! -d "${EXTRACTED_DIR}" ]]; then
  echo "Unable to locate extracted Verus directory under ${EXTRACT_ROOT}" >&2
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

if [[ ! -f "${INSTALL_DIR}/verus/verus" || ! -x "${INSTALL_DIR}/verus/verus" ]]; then
  echo "Verus binary missing or not executable after extraction." >&2
  if [[ -d "${BACKUP}" ]]; then
    rm -rf "${INSTALL_DIR}/verus"
    mv "${BACKUP}" "${INSTALL_DIR}/verus"
    echo "Restored previous installation." >&2
  fi
  exit 1
fi

rm -rf "${BACKUP}"

echo "[install-verus] operation=install path=\"${INSTALL_DIR}/verus/verus\"" >&2

cat <<EOM
Installed Verus ${VERUS_VERSION} in ${INSTALL_DIR}/verus
Export VERUS_BIN=${INSTALL_DIR}/verus/verus
EOM
