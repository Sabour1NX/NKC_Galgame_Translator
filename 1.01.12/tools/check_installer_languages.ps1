# SPDX-License-Identifier: MIT
# Run on a clean Windows test account after building the Inno installer.
$ErrorActionPreference='Stop'
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$dest=Join-Path $root 'build\inno-shortcuts-test'
$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Sabour1NX.NKCGalgameTranslator_is1'
if ((Test-Path -LiteralPath $dest) -or (Test-Path -LiteralPath $key)) {throw 'Existing installation'}
$dirs=@([Environment]::GetFolderPath('DesktopDirectory'),[Environment]::GetFolderPath('Programs'))
$zh=[string]::Concat([char]0x4e8c,[char]0x8272,[char]0x8776,'Galgame',[char]0x7ffb,[char]0x8bd1)
$en='NKC_Galgame_Translator'
foreach ($dir in $dirs) {foreach ($name in @($en,$zh)) {if (Test-Path -LiteralPath (Join-Path $dir ($name+'.lnk'))) {throw 'Shortcut name already in use'}}}
$version=Split-Path $root -Leaf
$exe=(Get-Item -LiteralPath (Join-Path $root "dist\NKC_Galgame_Translator-$version-winget-x64.exe")).FullName
$shell=New-Object -ComObject WScript.Shell
try {
    foreach ($lang in @('zh-CN','en-US','ja-JP')) {
        $process=Start-Process -FilePath $exe -ArgumentList @('/VERYSILENT','/SP-','/NORESTART','/SUPPRESSMSGBOXES',('/NKCLang='+$lang),('/DIR="'+$dest+'"')) -WindowStyle Hidden -PassThru -Wait
        if ($process.ExitCode) {throw "Installation failed: $lang"}
        $name=if ($lang -eq 'zh-CN') {$zh} else {$en}
        $other=if ($lang -eq 'zh-CN') {$en} else {$zh}
        foreach ($dir in $dirs) {
            $path=Join-Path $dir ($name+'.lnk')
            if (!(Test-Path -LiteralPath $path) -or $shell.CreateShortcut($path).TargetPath -ne (Join-Path $dest 'NKC_Galgame_Translator.exe')) {throw "Wrong shortcut: $lang"}
            if (Test-Path -LiteralPath (Join-Path $dir ($other+'.lnk'))) {throw 'Previous language shortcut was retained'}
        }
        Write-Output "$lang verified in both locations"
    }
} finally {
    $uninstall=Join-Path $dest 'unins000.exe'
    if (Test-Path -LiteralPath $uninstall) {
        $p=Start-Process -FilePath $uninstall -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART' -WindowStyle Hidden -PassThru -Wait
        if ($p.ExitCode -or (Test-Path -LiteralPath $key)) {throw 'Uninstall failed'}
    }
}
