param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..')).TrimEnd('\')
if ($projectRoot -eq [IO.Path]::GetPathRoot($projectRoot).TrimEnd('\')) { throw 'Refusing drive root.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'src\ufm') -PathType Container)) { throw 'Project marker missing.' }
$entries = @()
foreach ($name in @('.pytest_cache', '.mypy_cache', '.ruff_cache')) {
    $target = [IO.Path]::GetFullPath((Join-Path $projectRoot $name))
    if (-not $target.StartsWith($projectRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe cache path.' }
    if (-not (Test-Path -LiteralPath $target)) { continue }
    $item = Get-Item -Force -LiteralPath $target
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked cache.' }
    $children = @(Get-ChildItem -Force -Recurse -LiteralPath $target)
    if ($children | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }) { throw 'Linked cache child found.' }
    $files = @($children | Where-Object { -not $_.PSIsContainer })
    $size = ($files | Measure-Object -Property Length -Sum).Sum
    $entries += [PSCustomObject]@{ Path = $target; Files = $files.Count; Bytes = [long]$size; Removed = [bool]$Apply }
    if ($Apply) { Remove-Item -LiteralPath $target -Recurse -Force }
}
$report = [PSCustomObject]@{
    TimestampUtc = [DateTime]::UtcNow.ToString('o'); Applied = [bool]$Apply; Project = $projectRoot
    Entries = $entries
    Preserved = @('backups', '.runtime', '.tools', '.venv', '.venv312', 'linked-stack', 'graphify-out', 'dist', 'personal data')
}
$reportPath = Join-Path $projectRoot 'docs\CLEANUP_REPORT.json'
if (Test-Path -LiteralPath $reportPath) {
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
    $reportPath = Join-Path $projectRoot "docs\CLEANUP_REPORT-$stamp.json"
}
$report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $reportPath -Encoding utf8
$report
