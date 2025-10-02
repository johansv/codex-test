#!/usr/bin/env pwsh
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
Set-StrictMode -Version Latest
uv run pytest @Args
