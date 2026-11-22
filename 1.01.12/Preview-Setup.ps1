# SPDX-License-Identifier: MIT
# Launch a disposable copy of the newest built application's first-run wizard.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$program = 'NKC_Galgame_Translator.exe'
$layout = 'dist\NKC_Galgame_Translator'
function Test-Release([string]$folder) {
    (Test-Path -LiteralPath (Join-Path $folder $program) -PathType Leaf) -and
    (Test-Path -LiteralPath (Join-Path $folder 'SHA256SUMS.txt') -PathType Leaf)
}
$release = $null
if (Test-Release $PSScriptRoot) {
    $release = $PSScriptRoot
} elseif (Test-Release (Join-Path $PSScriptRoot $layout)) {
    $release = Join-Path $PSScriptRoot $layout
} else {
    $versions = Get-ChildItem -LiteralPath $PSScriptRoot -Directory |
        Where-Object { $_.Name -match '^\d+\.\d{2}\.\d{2}$' } |
        Sort-Object { [version]$_.Name } -Descending
    foreach ($version in $versions) {
        $candidate = Join-Path $version.FullName $layout
        if (Test-Release $candidate) { $release = $candidate; break }
    }
}
if (!$release) { throw 'No built release found. Extract the Windows x64 portable ZIP and run Preview-Setup.cmd inside it.' }

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$leaf = 'NKC-Setup-' + [guid]::NewGuid().ToString('N')
$preview = Join-Path $tempBase $leaf
New-Item -ItemType Directory -Path $preview -ErrorAction Stop | Out-Null
$sha = [Security.Cryptography.SHA256]::Create()
try {
    foreach ($entry in [IO.File]::ReadLines((Join-Path $release 'SHA256SUMS.txt'))) {
        if ($entry -notmatch '^([0-9a-f]{64})  (.+)$') { throw 'Invalid release manifest.' }
        $expected = $Matches[1]
        $relative = $Matches[2]
        if ($relative -notmatch '^(_internal/|assets/|native/bin/|models/|docs/|tools/ocr_helper/|config/example\.json$|NKC_Galgame_Translator\.exe$)') { continue }
        if ($relative -match '(^|/)\.\.?(/|$)|[:\\]') { throw 'Invalid package path.' }
        $destination = Join-Path $preview $relative
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
        [IO.File]::Copy((Join-Path $release $relative), $destination)
        $stream = [IO.File]::OpenRead($destination)
        try { $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
        finally { $stream.Dispose() }
        if ($digest -ne $expected) {
            throw "Release file failed verification: $relative"
        }
    }
    Write-Output "First-run preview: $release"
    $process = Start-Process -FilePath (Join-Path $preview $program) -WorkingDirectory $preview -PassThru
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) { throw "Application exited with code $($process.ExitCode)." }
} finally {
    $sha.Dispose()
    $resolved = (Resolve-Path -LiteralPath $preview).ProviderPath
    if ([IO.Path]::GetDirectoryName($resolved) -ne $tempBase -or [IO.Path]::GetFileName($resolved) -ne $leaf) {
        throw 'Unexpected preview directory; cleanup stopped.'
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
