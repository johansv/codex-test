#!/usr/bin/env bash
set -euo pipefail
uv run python -m agentlab.cli.dev "$@"
