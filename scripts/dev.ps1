#!/usr/bin/env pwsh
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
Set-StrictMode -Version Latest
uv run python -m agentlab.cli.dev @Args
