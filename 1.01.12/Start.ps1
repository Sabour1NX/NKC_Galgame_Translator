$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$personal = Join-Path $PSScriptRoot 'demo\Private\NKC_Galgame_Translator.exe'
if (Test-Path -LiteralPath $personal -PathType Leaf) {
    Start-Process -FilePath $personal -WorkingDirectory (Split-Path -Parent $personal) -WindowStyle Hidden
    return
}
$packaged = Join-Path $PSScriptRoot 'dist\NKC_Galgame_Translator\NKC_Galgame_Translator.exe'
if (Test-Path -LiteralPath $packaged -PathType Leaf) {
    Start-Process -FilePath $packaged -WorkingDirectory (Split-Path -Parent $packaged) -WindowStyle Hidden
    return
}
$pythonw = Join-Path $PSScriptRoot 'vendor\python\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) {
    $pythonw = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
}
if (-not $pythonw) { $pythonw = (Get-Command python.exe).Source }
Start-Process -FilePath $pythonw -ArgumentList 'main.py' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
