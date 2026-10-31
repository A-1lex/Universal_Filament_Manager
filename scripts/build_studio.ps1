param(
    [string]$DestinationParent = 'D:\',
    [string]$PythonExe,
    [string]$SigningCertificateThumbprint,
    [string]$TimestampServer
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not $PythonExe) { $PythonExe = Join-Path $projectRoot '.venv312\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) { throw 'Python not found.' }
if ([bool]$SigningCertificateThumbprint -ne [bool]$TimestampServer) {
    throw 'Signing requires both SigningCertificateThumbprint and TimestampServer.'
}
$outputFolder = Join-Path $DestinationParent 'UFM Studio'
if (Test-Path -LiteralPath $outputFolder) { throw "Output already exists: $outputFolder. Use a new DestinationParent to preserve the installed copy." }
Push-Location $projectRoot
$previousVersionFile = $env:UFM_VERSION_FILE
try {
    $versionFile = Join-Path $projectRoot '.runtime\build-metadata\ufm_version_info.txt'
    New-Item -ItemType Directory -Path (Split-Path -Parent $versionFile) -Force | Out-Null
    & $PythonExe scripts/write_pyinstaller_version.py $versionFile
    if ($LASTEXITCODE -ne 0) { throw 'Windows executable version metadata generation failed.' }
    $env:UFM_VERSION_FILE = $versionFile
    & (Join-Path $PSScriptRoot 'prepare_node_runtime.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Node runtime preparation failed.' }
    & $PythonExe scripts/sync_haspel_calculation_resources.py
    if ($LASTEXITCODE -ne 0) { throw 'Haspel calculation resource sync failed.' }
    & $PythonExe scripts/create_studio_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
    & $PythonExe -m PyInstaller --distpath $DestinationParent `
        --workpath .runtime/studio-build scripts/ufm_studio.spec
    if ($LASTEXITCODE -ne 0) { throw 'Studio build failed.' }
    if ($SigningCertificateThumbprint) {
        & (Join-Path $PSScriptRoot 'sign_windows_artifact.ps1') `
            -Path (Join-Path $outputFolder 'UFM Studio.exe') `
            -CertificateThumbprint $SigningCertificateThumbprint `
            -TimestampServer $TimestampServer
        if ($LASTEXITCODE -ne 0) { throw 'Studio executable signing failed.' }
    }
    Copy-Item -LiteralPath src/ufm/ui/assets/ufm.ico -Destination $outputFolder
    Copy-Item -LiteralPath THIRD_PARTY_NOTICES.md -Destination $outputFolder
    & $PythonExe scripts/collect_studio_notices.py (Join-Path $outputFolder 'third-party')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency notice collection failed.' }
    & $PythonExe scripts/write_studio_manifest.py $outputFolder
    if ($LASTEXITCODE -ne 0) { throw 'Studio build manifest generation failed.' }
    Write-Output "Built: $outputFolder"
}
finally {
    $env:UFM_VERSION_FILE = $previousVersionFile
    Pop-Location
}
