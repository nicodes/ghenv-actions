#!/usr/bin/env bash
set -euo pipefail
umask 077

[[ "${RUNNER_OS:-}" == Linux ]] || { echo 'ghenv-actions requires a Linux runner' >&2; exit 1; }
[[ "${GHENV_ENVIRONMENT:-}" == Preview ]] || { echo 'Only Preview is permitted' >&2; exit 1; }
[[ "${GHENV_REQUEST_ID:-}" =~ ^[a-f0-9]{32}$ ]] || { echo 'Invalid request ID' >&2; exit 1; }
[[ -n "${GHENV_PUBLIC_KEY:-}" ]] || { echo 'A public key is required' >&2; exit 1; }

read -r source_commit < "$GHENV_ACTION_PATH/ghenv-source"
[[ "$source_commit" =~ ^[a-f0-9]{40}$ ]] || { echo 'Invalid exporter source pin' >&2; exit 1; }
state_dir="$(mktemp -d "$RUNNER_TEMP/ghenv-action.XXXXXXXX")"
trap 'rm -rf -- "$state_dir"' ERR
printf 'state-dir=%s\n' "$state_dir" >> "$GITHUB_OUTPUT"
mkdir "$state_dir/bin"
# Fetch the exact commit into a private directory, independent of both the
# consumer workspace and the exporter's default branch/release state.
git init --quiet "$state_dir/source"
git -C "$state_dir/source" fetch --quiet --depth=1 https://github.com/nicodes/ghenv.git "$source_commit"
git -C "$state_dir/source" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$state_dir/source" rev-parse HEAD)" == "$source_commit" ]] || { echo 'Exporter commit mismatch' >&2; exit 1; }
GOWORK=off GOFLAGS= go -C "$state_dir/source" build -mod=readonly -trimpath -o "$state_dir/bin/ghenv" .
