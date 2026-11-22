param([Parameter(Mandatory)][string]$Executable,
      [Parameter(Mandatory)][string]$Label,
      [Parameter(Mandatory)][string]$AlternateLabel,
      [string]$TestRoot)
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
if ($TestRoot) {
    $folders = @((Join-Path $TestRoot 'Desktop'), (Join-Path $TestRoot 'Programs'))
} else {
    $folders = @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))
}
foreach ($folder in $folders) {
    [IO.Directory]::CreateDirectory($folder) | Out-Null
    $path = Join-Path $folder ($Label + '.lnk')
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $Executable
    $link.WorkingDirectory = Split-Path -Parent $Executable
    $link.IconLocation = $Executable + ',0'
    $link.Save()
    $old = Join-Path $folder ($AlternateLabel + '.lnk')
    if ([IO.File]::Exists($old)) {
        $previous = $shell.CreateShortcut($old)
        if ($previous.TargetPath -eq $Executable) { [IO.File]::Delete($old) }
    }
    if ($shell.CreateShortcut($path).TargetPath -ne $Executable) { throw 'Shortcut target mismatch' }
}
