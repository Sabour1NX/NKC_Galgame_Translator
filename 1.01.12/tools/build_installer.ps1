# SPDX-License-Identifier: MIT
[CmdletBinding()]
param([string]$Compiler, [switch]$TestFixture)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$version = Split-Path -Leaf $root
if (!$Compiler) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $Compiler = $command.Source }
    else { $Compiler = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Inno Setup 6\ISCC.exe' }
}
$report = Get-Content -LiteralPath (Join-Path $root 'reports\package-verification.json') -Raw | ConvertFrom-Json
$name = "NKC_Galgame_Translator-$version-windows-x64.zip"
$zip = Join-Path $root "dist\$name"
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash
if (!$report.passed -or $report.version -ne $version -or $hash -ne $report.checks.archives.sha256.$name) {
    throw 'The public ZIP must match the verified release.'
}
$build = [IO.Directory]::CreateDirectory((Join-Path $root 'build')).FullName
$stage = [IO.Directory]::CreateDirectory((Join-Path $build ([Guid]::NewGuid().ToString('N')))).FullName
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::ExtractToDirectory($zip, $stage)
    $payload = Join-Path $stage 'NKC_Galgame_Translator'
    $options = @("/DAppVersionText=$version", "/DPayloadRoot=$payload")
    if ($TestFixture) { $options += '/DSetupFixture' }
    & $Compiler @options (Join-Path $PSScriptRoot 'setup.iss')
    if ($LASTEXITCODE) { throw 'Inno Setup compilation failed.' }
} finally {
    $resolved = (Resolve-Path -LiteralPath $stage).Path
    if ((Split-Path $resolved -Parent) -ne $build -or (Split-Path $resolved -Leaf) -notmatch '^[0-9a-f]{32}$') { throw 'Unexpected staging path.' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
if (!$TestFixture) {
    $file = Get-Item -LiteralPath (Join-Path $root "dist\NKC_Galgame_Translator-$version-setup.exe")
    $digest = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    Set-Content -LiteralPath (Join-Path $file.DirectoryName ($file.BaseName+'-SHA256.txt')) -Value "$digest  $($file.Name)" -Encoding ascii
}
