#!/usr/bin/env bash
set -euo pipefail
REPO="https://github.com/cleziotc/pp5ci-hotspot.git"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || pwd)"
if [[ -f "${ROOT_DIR}/scripts/install-common.sh" ]]; then
  exec bash "${ROOT_DIR}/scripts/install-common.sh" vm
fi
[[ "${EUID}" -eq 0 ]] || { echo "Execute com sudo." >&2; exit 1; }
apt-get update
apt-get install -y git ca-certificates
TMP="$(mktemp -d)"
trap 'rm -rf "${TMP}"' EXIT
git clone --depth 1 "${REPO}" "${TMP}/pp5ci-hotspot"
exec bash "${TMP}/pp5ci-hotspot/scripts/install-common.sh" vm
