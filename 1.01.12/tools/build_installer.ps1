# SPDX-License-Identifier: MIT
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$version = Split-Path -Leaf $projectRoot
$packageName = "NKC_Galgame_Translator-$version"
$zip = Join-Path $projectRoot "dist\$packageName-windows-x64.zip"
$report = Join-Path $projectRoot 'reports\package-verification.json'
if (!(Test-Path -LiteralPath $report) -or !(Get-Content -LiteralPath $report -Raw | ConvertFrom-Json).passed) {
    throw 'Verify the public release before building the installer.'
}
$tmp = Join-Path $projectRoot 'build\installer'
$package = Join-Path $tmp 'release.zip'
New-Item -Path $tmp -ItemType Directory -Force | Out-Null
Copy-Item -LiteralPath $zip -Destination $package -Force
$python = Join-Path $projectRoot 'vendor\python\python.exe'
$name = "NKC_Galgame_Translator-$version-setup"
$dist = Join-Path $projectRoot 'dist'
$arguments = @('-m','PyInstaller','--noconfirm','--noupx','--windowed','--onefile','--name',$name,
    '--distpath',$dist,'--workpath',(Join-Path $tmp 'pyinstaller'),'--specpath',$tmp,
    '--icon',(Join-Path $projectRoot 'assets\taiji.ico'),
    '--add-data',($package + ';.'),
    '--add-data',((Join-Path $PSScriptRoot 'install_shortcuts.ps1') + ';.'),
    '--add-data',((Join-Path $PSScriptRoot 'install_strings.json') + ';.'),
    (Join-Path $PSScriptRoot 'installer.py'))
& $python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed.' }
$exe = Join-Path $dist "$name.exe"
$installerTest = Join-Path $projectRoot 'reports\installer-selftest.json'
$process = Start-Process -FilePath $exe -ArgumentList @('--self-test',('"' + $installerTest + '"')) -WindowStyle Hidden -PassThru
if (!$process.WaitForExit(150000) -or $process.ExitCode -ne 0) { throw 'Installer self-test failed.' }
$result = Get-Content -LiteralPath $installerTest -Raw | ConvertFrom-Json
if (!$result.passed -or ($result.version -ne $version)) { throw 'Installer verification failed.' }
$checksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe).Hash.ToLowerInvariant()
Set-Content -LiteralPath (Join-Path $dist "$name-SHA256.txt") -Value "$checksum  $name.exe" -Encoding ascii
Write-Output "Installer: $exe"
