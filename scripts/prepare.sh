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
prepare_status=0
trap 'prepare_status=$?; if [[ "$prepare_status" -ne 0 ]]; then rm -rf -- "$state_dir"; fi' EXIT
printf 'state-dir=%s\n' "$state_dir" >> "$GITHUB_OUTPUT"
mkdir "$state_dir/bin"
# Fetch the exact commit into a private directory, independent of both the
# consumer workspace and the exporter's default branch/release state.
git init --quiet "$state_dir/source"
git -C "$state_dir/source" fetch --quiet --depth=1 https://github.com/nicodes/ghenv.git "$source_commit"
git -C "$state_dir/source" checkout --quiet --detach FETCH_HEAD
[[ "$(git -C "$state_dir/source" rev-parse HEAD)" == "$source_commit" ]] || { echo 'Exporter commit mismatch' >&2; exit 1; }
# Build only the reviewed checkout, with a private Cargo home and target tree.
# Consumer Cargo config and inherited compiler hooks cannot select other code.
cargo_binary="$(rustup which --toolchain 1.94.0 cargo)"
rustc_binary="$(rustup which --toolchain 1.94.0 rustc)"
[[ -x "$cargo_binary" && -x "$rustc_binary" ]] || { echo 'Pinned Rust tools are missing' >&2; exit 1; }
(
  cd "$state_dir/source"
  env -i HOME="$HOME" PATH="$PATH" RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}" \
    CARGO_HOME="$state_dir/cargo-home" RUSTC="$rustc_binary" VERSION=dev COMMIT="$source_commit" \
    "$cargo_binary" build --locked --release --target-dir "$state_dir/target"
)
cp "$state_dir/target/release/ghenv" "$state_dir/bin/ghenv"
