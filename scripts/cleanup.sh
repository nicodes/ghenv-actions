#!/usr/bin/env bash
set -euo pipefail

[[ -n "${GHENV_STATE_DIR:-}" ]] || exit 0
relative="${GHENV_STATE_DIR#"$RUNNER_TEMP"/}"
if [[ "$GHENV_STATE_DIR" == "$RUNNER_TEMP"/ghenv-action.* && "$relative" != */* ]]; then
  rm -rf -- "$GHENV_STATE_DIR"
else
  echo 'Refusing to clean a path outside the action temporary directory' >&2
  exit 1
fi
