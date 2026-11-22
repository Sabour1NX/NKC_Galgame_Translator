# SPDX-License-Identifier: MIT
# Cancel this project's explicit idle watcher; no administrator permission needed.
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$stopFile = Join-Path $projectRoot 'data\idle_shutdown.stop'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stopFile) | Out-Null
Set-Content -LiteralPath $stopFile -Value 'cancel' -Encoding ascii
Write-Output 'Idle shutdown cancelled.'
