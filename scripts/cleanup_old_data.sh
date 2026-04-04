#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DATA_DIR="${1:-${PROJECT_DIR}/data}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

if [[ ! -d "${DATA_DIR}" ]]; then
  echo "data directory not found: ${DATA_DIR}" >&2
  exit 1
fi

cutoff_epoch="$(date -d "${RETENTION_DAYS} days ago" +%s)"

find "${DATA_DIR}" -mindepth 1 -maxdepth 1 -type d | while read -r dir; do
  name="$(basename "${dir}")"

  if [[ ! "${name}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    continue
  fi

  dir_epoch="$(date -d "${name}" +%s 2>/dev/null || true)"
  if [[ -z "${dir_epoch}" ]]; then
    continue
  fi

  if (( dir_epoch < cutoff_epoch )); then
    echo "deleting ${dir}"
    rm -rf "${dir}"
  fi
done
