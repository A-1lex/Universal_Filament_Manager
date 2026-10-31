param([string]$DataDir, [string]$Locale = 'uk-UA')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonExe = $null
foreach ($relative in @('.venv312\Scripts\python.exe', '.venv\Scripts\python.exe')) {
    $candidate = Join-Path $projectRoot $relative
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
        & $candidate -c 'import PySide6' 2>$null
        if ($LASTEXITCODE -eq 0) { $pythonExe = $candidate; break }
    }
}
if (-not $pythonExe) { throw 'Немає Python із PySide6. Установіть залежності .[desktop] у середовище проєкту.' }
$arguments = @('-m', 'ufm.ui.studio', '--locale', $Locale)
if ($DataDir) { $arguments += @('--data-dir', $DataDir) }
Push-Location $projectRoot
try { & $pythonExe @arguments; exit $LASTEXITCODE }
finally { Pop-Location }
