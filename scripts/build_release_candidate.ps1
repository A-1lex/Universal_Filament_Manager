param(
    [Parameter(Mandatory = $true)][string]$DestinationParent,
    [string]$SigningCertificateThumbprint,
    [string]$TimestampServer
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$destinationParentPath = [IO.Path]::GetFullPath($DestinationParent)
$bundlePath = Join-Path $destinationParentPath 'UFM Studio'
$sbomPath = Join-Path $destinationParentPath 'UFM Studio.cdx.json'
if (Test-Path -LiteralPath $bundlePath) {
    throw "Output already exists: $bundlePath. Use a new DestinationParent to preserve the existing candidate."
}
if (Test-Path -LiteralPath $sbomPath) {
    throw "SBOM output already exists: $sbomPath. Use a new DestinationParent to preserve it."
}
$probePath = $destinationParentPath
while ($probePath) {
    $existingPath = Get-Item -Force -LiteralPath $probePath -ErrorAction SilentlyContinue
    if ($existingPath -and ($existingPath.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing a linked release destination component: $($existingPath.FullName)"
    }
    $parentPath = Split-Path -Parent $probePath
    if (-not $parentPath -or $parentPath -eq $probePath) { break }
    $probePath = $parentPath
}
$releaseEnvironmentPath = Join-Path $projectRoot '.venv-release'
$environmentItem = Get-Item -Force -LiteralPath $releaseEnvironmentPath -ErrorAction SilentlyContinue
if ($environmentItem -and ($environmentItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw 'Refusing a linked release environment.'
}
$uv = Get-Command uv.exe -ErrorAction SilentlyContinue
if (-not $uv) { throw 'uv.exe not found; install Astral uv before preparing the locked release environment.' }
if ([bool]$SigningCertificateThumbprint -ne [bool]$TimestampServer) {
    throw 'Signing requires both SigningCertificateThumbprint and TimestampServer.'
}

$previousEnvironment = $env:UV_PROJECT_ENVIRONMENT
try {
    $env:UV_PROJECT_ENVIRONMENT = $releaseEnvironmentPath
    & $uv.Source sync --locked --python 3.12.15 --extra desktop --extra build --project $projectRoot
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE." }
}
finally {
    $env:UV_PROJECT_ENVIRONMENT = $previousEnvironment
}

$python = Join-Path $releaseEnvironmentPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Locked release Python environment was not created: $python"
}
$studioBuildArguments = @{
    DestinationParent = $destinationParentPath
    PythonExe = $python
}
if ($SigningCertificateThumbprint) {
    $studioBuildArguments.SigningCertificateThumbprint = $SigningCertificateThumbprint
    $studioBuildArguments.TimestampServer = $TimestampServer
}
& (Join-Path $PSScriptRoot 'build_studio.ps1') @studioBuildArguments
if ($LASTEXITCODE -ne 0) { throw "Studio bundle build failed with exit code $LASTEXITCODE." }
$nodePath = Join-Path $bundlePath '_internal\runtime\node.exe'
$nodeItem = Get-Item -LiteralPath $nodePath -ErrorAction Stop
$nodeVersion = $nodeItem.VersionInfo.ProductVersion
if ($nodeVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "Bundled Node executable has no expected PE ProductVersion: $nodeVersion"
}
$qtRoot = Join-Path $bundlePath '_internal\PySide6'
$qtDlls = @(Get-ChildItem -LiteralPath $qtRoot -Recurse -File -Filter '*.dll' |
    Where-Object {
        $_.Name -like 'Qt6*.dll' -or $_.FullName -match '[\\/]plugins[\\/].+\.dll$'
    })
if (-not $qtDlls.Count) { throw 'No bundled Qt runtime DLLs were found.' }
$qtVersions = @($qtDlls | ForEach-Object {
    ([string]$_.VersionInfo.ProductVersion).Trim() -replace '\.0$', ''
} | Select-Object -Unique)
if ($qtVersions.Count -ne 1 -or $qtVersions[0] -notmatch '^\d+\.\d+\.\d+$') {
    throw "Bundled Qt DLLs have missing or mixed PE ProductVersion values: $($qtVersions -join ', ')"
}
$qtVersion = $qtVersions[0]
& $python (Join-Path $PSScriptRoot 'write_release_sbom.py') $bundlePath $sbomPath `
    --node-version $nodeVersion --qt-version $qtVersion
if ($LASTEXITCODE -ne 0) { throw "Release SBOM generation failed with exit code $LASTEXITCODE." }
Write-Output "SBOM: $sbomPath"
