# SPDX-License-Identifier: MIT
$ErrorActionPreference = 'Stop'
$nativeRoot = $PSScriptRoot
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (!(Test-Path -LiteralPath $vswhere)) { throw 'Install Visual Studio Build Tools with Desktop development with C++.' }
$vsRoot = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (!$vsRoot) { throw 'MSVC x64 build tools were not found.' }
$vcvars = Join-Path $vsRoot 'VC\Auxiliary\Build\vcvars64.bat'
$binDir = Join-Path $nativeRoot 'bin'
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
# Only the installed vendor environment script is run by cmd. Project paths
# never enter a generated batch file: Unicode, ampersands and percent signs in
# a checkout name must remain ordinary arguments, not shell expansion/code.
if ($vcvars.Contains('"') -or $vcvars.Contains('%')) { throw 'Unexpected vendor environment path.' }
$vendorCommand = '"' + $vcvars + '" >nul && set'
$environmentLines = & $env:ComSpec /d /c $vendorCommand
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment initialization failed.' }
foreach ($entry in $environmentLines) {
    $separator = $entry.IndexOf('=')
    if ($separator -gt 0) {
        [Environment]::SetEnvironmentVariable($entry.Substring(0,$separator),$entry.Substring($separator+1),'Process')
    }
}
$compiler = Join-Path $env:VCToolsInstallDir 'bin\Hostx64\x64\cl.exe'
$compilerArgs = @('/nologo','/std:c++17','/EHsc','/O2','/MT','/W4','/utf-8',
    '/DUNICODE','/D_UNICODE','/GS','/sdl','/guard:cf','/LD','core.cpp',
    ('/Fo'+(Join-Path $binDir 'core.obj')),('/Fe'+(Join-Path $binDir 'nkc_galgame_translator_core.dll')),
    '/link','windowsapp.lib','user32.lib','gdi32.lib','dwmapi.lib','d3d11.lib','dxgi.lib','/MACHINE:X64',
    '/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/GUARD:CF')
Push-Location -LiteralPath $nativeRoot
try {
    & $compiler @compilerArgs
    if ($LASTEXITCODE -ne 0) { throw "Native build failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
Write-Output "Built $binDir\nkc_galgame_translator_core.dll"
