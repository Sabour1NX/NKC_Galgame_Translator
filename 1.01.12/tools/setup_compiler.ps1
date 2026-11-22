$ErrorActionPreference = 'Stop'
$vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$installation = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'MSVC x64 build tools not found' }
$msvc = Get-ChildItem (Join-Path $installation 'VC\Tools\MSVC') -Directory | Sort-Object Name -Descending | Select-Object -First 1
$sdkRoot = 'C:\Program Files (x86)\Windows Kits\10'
$sdk = Get-ChildItem (Join-Path $sdkRoot 'Include') -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'um\Windows.h') } | Sort-Object Name -Descending | Select-Object -First 1
$compilerBin = Join-Path $msvc.FullName 'bin\Hostx64\x64'
$sdkBin = Join-Path $sdkRoot "bin\$($sdk.Name)\x64"
$cmakeBin = Join-Path $installation 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin'
$ninjaBin = Join-Path $installation 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja'
$additions = @($compilerBin, $sdkBin, $cmakeBin, $ninjaBin) | Where-Object { Test-Path $_ }
$oldPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$oldInclude = [Environment]::GetEnvironmentVariable('INCLUDE', 'User')
$oldLib = [Environment]::GetEnvironmentVariable('LIB', 'User')
$backup = Join-Path $PSScriptRoot '..\config\compiler_env_backup.json'
if (-not (Test-Path $backup)) { @{ Path=$oldPath; INCLUDE=$oldInclude; LIB=$oldLib } | ConvertTo-Json | Set-Content -LiteralPath $backup -Encoding utf8 }
$parts = @($oldPath -split ';' | Where-Object { $_ })
foreach ($p in $additions) { if ($parts -notcontains $p) { $parts += $p } }
$include = @((Join-Path $msvc.FullName 'include'))
foreach ($p in @('ucrt','shared','um','winrt','cppwinrt')) { $include += Join-Path $sdk.FullName $p }
$lib = @((Join-Path $msvc.FullName 'lib\x64'), (Join-Path $sdkRoot "Lib\$($sdk.Name)\ucrt\x64"), (Join-Path $sdkRoot "Lib\$($sdk.Name)\um\x64"))
if ($oldInclude) { $include += $oldInclude }
if ($oldLib) { $lib += $oldLib }
[Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
[Environment]::SetEnvironmentVariable('INCLUDE', (($include | Select-Object -Unique) -join ';'), 'User')
[Environment]::SetEnvironmentVariable('LIB', (($lib | Select-Object -Unique) -join ';'), 'User')
$env:Path = ($additions -join ';') + ';' + $env:Path
$env:INCLUDE = ($include | Select-Object -Unique) -join ';'
$env:LIB = ($lib | Select-Object -Unique) -join ';'
Write-Output "Configured MSVC $($msvc.Name) x64; SDK $($sdk.Name). Restart terminal to inherit user environment."
& (Join-Path $compilerBin 'cl.exe') 2>&1 | ForEach-Object { "$_" }
