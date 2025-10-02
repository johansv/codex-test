#!/usr/bin/env pwsh
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot ".." )).Path
$approval = if (![string]::IsNullOrWhiteSpace($env:CODEX_APPROVAL_POLICY)) { $env:CODEX_APPROVAL_POLICY } else { "never" }
$sandbox = if (![string]::IsNullOrWhiteSpace($env:CODEX_SANDBOX)) { $env:CODEX_SANDBOX } else { "danger-full-access" }

$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) {
    throw 'Codex CLI not found on PATH. Install it with "npm install -g @openai/codex".'
}

& $codex.Path --ask-for-approval $approval --sandbox $sandbox --cd $repoRoot @Args
exit $LASTEXITCODE
