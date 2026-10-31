param(
    [string]$InstallRoot = 'D:\UFM Studio',
    [string]$DataDir,
    [string]$DesktopPath
)
$ErrorActionPreference = 'Stop'
$resolvedInstall = [IO.Path]::GetFullPath($InstallRoot)
$executable = Join-Path $resolvedInstall 'UFM Studio.exe'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw "EXE not found: $executable" }
if (-not $DesktopPath) { $DesktopPath = [Environment]::GetFolderPath('DesktopDirectory') }
if (-not (Test-Path -LiteralPath $DesktopPath -PathType Container)) { throw 'Desktop folder not found.' }
$shortcutPath = Join-Path $DesktopPath 'UFM Studio.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $executable
$shortcut.WorkingDirectory = $resolvedInstall
$shortcut.Description = 'UFM Studio - filament inventory and local printers'
$shortcut.IconLocation = (Join-Path $resolvedInstall 'ufm.ico') + ',0'
if ($DataDir) {
    $resolvedData = [IO.Path]::GetFullPath($DataDir)
    if ($resolvedData.Contains('"')) { throw 'Invalid data path.' }
    $shortcut.Arguments = '--data-dir "' + $resolvedData + '"'
}
else { $shortcut.Arguments = '' }
$shortcut.Save()
$verified = $shell.CreateShortcut($shortcutPath)
if ($verified.TargetPath -ne $executable) { throw 'Shortcut validation failed.' }
[PSCustomObject]@{ Shortcut = $shortcutPath; Target = $verified.TargetPath; Arguments = $verified.Arguments }
