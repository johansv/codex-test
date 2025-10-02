#!/usr/bin/env bash
set -euo pipefail

APPROVAL_POLICY=${CODEX_APPROVAL_POLICY:-on-request}
SANDBOX_MODE=${CODEX_SANDBOX:-workspace-write}

if ! codex_stub=$(command -v codex 2>/dev/null); then
  echo "Codex CLI not found on PATH. Install it with 'npm install -g @openai/codex'." >&2
  exit 1
fi

codex_bin="$codex_stub"
binary_suffix=""
module_dir="$(dirname "$codex_stub")/node_modules/@openai/codex"

if [[ -d "$module_dir/vendor" ]]; then
  uname_s=$(uname -s)
  uname_m=$(uname -m)
  platform=""
  case "$uname_s" in
    Linux)
      case "$uname_m" in
        x86_64) platform="x86_64-unknown-linux-musl" ;;
        aarch64|arm64) platform="aarch64-unknown-linux-musl" ;;
      esac
      ;;
    Darwin)
      case "$uname_m" in
        x86_64) platform="x86_64-apple-darwin" ;;
        arm64) platform="aarch64-apple-darwin" ;;
      esac
      ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT)
      case "$uname_m" in
        x86_64|amd64|AMD64) platform="x86_64-pc-windows-msvc" ;;
        arm64|ARM64) platform="aarch64-pc-windows-msvc" ;;
      esac
      binary_suffix=".exe"
      ;;
  esac

  if [[ -n "$platform" ]]; then
    candidate="$module_dir/vendor/$platform/codex/codex$binary_suffix"
    if [[ -x "$candidate" ]]; then
      codex_bin="$candidate"
    fi
  fi
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

exec "$codex_bin" --ask-for-approval "$APPROVAL_POLICY" --sandbox "$SANDBOX_MODE" --cd "$repo_root" "$@"
