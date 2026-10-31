param(
    [Parameter(Mandatory = $true)][string]$BundleDir,
    [Parameter(Mandatory = $true)][string]$OutputDir,
    [string]$CompilerPath,
    [string]$PythonExe,
    [string]$SigningCertificateThumbprint,
    [string]$TimestampServer
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$bundlePath = [IO.Path]::GetFullPath($BundleDir)
$outputPath = [IO.Path]::GetFullPath($OutputDir)
$issPath = Join-Path $PSScriptRoot 'ufm_studio.iss'
if ([bool]$SigningCertificateThumbprint -ne [bool]$TimestampServer) {
    throw 'Signing requires both SigningCertificateThumbprint and TimestampServer.'
}
if ([string]::IsNullOrWhiteSpace($SigningCertificateThumbprint) -or
    [string]::IsNullOrWhiteSpace($TimestampServer)) {
    throw 'A public-release installer requires an approved signing certificate and timestamp server.'
}
$requiredSignerThumbprint = ($SigningCertificateThumbprint -replace '\s', '').ToUpperInvariant()
if ($requiredSignerThumbprint -notmatch '^[0-9A-F]{40}$') {
    throw 'SigningCertificateThumbprint must be one SHA-1 certificate thumbprint.'
}
$bundlePrefix = $bundlePath.TrimEnd('\') + '\'
if ($outputPath.Equals($bundlePath, [StringComparison]::OrdinalIgnoreCase) -or
    $outputPath.StartsWith($bundlePrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Installer output must be outside the verified bundle directory.'
}
$probePath = $outputPath
while ($probePath) {
    $existingPath = Get-Item -Force -LiteralPath $probePath -ErrorAction SilentlyContinue
    if ($existingPath -and ($existingPath.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "Refusing an installer output path with a link or junction component: $($existingPath.FullName)"
    }
    $parentPath = Split-Path -Parent $probePath
    if (-not $parentPath -or $parentPath -eq $probePath) { break }
    $probePath = $parentPath
}

if (-not (Test-Path -LiteralPath $bundlePath -PathType Container)) {
    throw "Bundle directory not found: $bundlePath"
}
foreach ($relative in @('UFM Studio.exe', 'ufm.ico', 'THIRD_PARTY_NOTICES.md',
                         'third-party\runtime-dependencies.json', 'build-manifest.json')) {
    $file = Join-Path $bundlePath $relative
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Required bundle file not found: $file"
    }
}

if (-not $PythonExe) { $PythonExe = Join-Path $projectRoot '.venv312\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python verifier not found: $PythonExe"
}
& $PythonExe (Join-Path $PSScriptRoot 'write_studio_manifest.py') $bundlePath --verify
if ($LASTEXITCODE -ne 0) { throw 'Bundle integrity verification failed.' }

if (-not $CompilerPath) {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { $CompilerPath = $command.Source }
}
if (-not $CompilerPath) {
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    )) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $CompilerPath = $candidate
            break
        }
    }
}
if (-not $CompilerPath -or -not (Test-Path -LiteralPath $CompilerPath -PathType Leaf)) {
    throw 'Inno Setup ISCC.exe not found. Install Inno Setup 6 or pass -CompilerPath.'
}

$manifest = Get-Content -LiteralPath (Join-Path $bundlePath 'build-manifest.json') -Raw |
    ConvertFrom-Json
if (-not $manifest.version -or $manifest.artifact_type -ne 'windows-folder') {
    throw 'Bundle manifest has no valid Windows-folder version.'
}
if ([string]$manifest.version -notmatch '^\d+\.\d+\.\d+$') {
    throw 'A public-release installer requires a stable three-part version without a development or prerelease suffix.'
}
$sourceProvenance = $manifest.source_provenance
if (-not $sourceProvenance -or
    [string]$sourceProvenance.source_git_revision -notmatch '^[0-9a-f]{40,64}$' -or
    $sourceProvenance.source_git_worktree_clean -ne $true -or
    [string]$sourceProvenance.input_tree_sha256 -notmatch '^[0-9a-f]{64}$' -or
    [int]$sourceProvenance.input_file_count -le 0) {
    throw 'A public-release installer requires a clean Git source revision and verified source-input manifest.'
}
$manifestPath = Join-Path $bundlePath 'build-manifest.json'
$manifestHash = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
$sbomPath = Join-Path (Split-Path -Parent $bundlePath) 'UFM Studio.cdx.json'
if (-not (Test-Path -LiteralPath $sbomPath -PathType Leaf)) {
    throw "Matching CycloneDX sidecar not found: $sbomPath. Build the candidate with build_release_candidate.ps1 first."
}
$sbom = Get-Content -LiteralPath $sbomPath -Raw | ConvertFrom-Json
if ($sbom.bomFormat -ne 'CycloneDX' -or $sbom.specVersion -ne '1.7') {
    throw 'Installer requires a CycloneDX 1.7 BOM sidecar.'
}
if ($sbom.metadata.component.version -ne [string]$manifest.version) {
    throw 'SBOM version does not match the bundle manifest.'
}
$sbomManifestHashes = @($sbom.metadata.component.properties |
    Where-Object { $_.name -eq 'ufm:bundle-manifest-sha256' } |
    ForEach-Object { [string]$_.value })
if ($sbomManifestHashes.Count -ne 1 -or $sbomManifestHashes[0] -ne $manifestHash) {
    throw 'SBOM does not identify the exact bundle manifest hash.'
}
$sbomRuntimeInventoryHashes = @($sbom.metadata.component.properties |
    Where-Object { $_.name -eq 'ufm:runtime-inventory-sha256' } |
    ForEach-Object { [string]$_.value })
$runtimeInventoryPath = Join-Path $bundlePath 'third-party\runtime-dependencies.json'
$runtimeInventoryHash = (Get-FileHash -LiteralPath $runtimeInventoryPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sbomRuntimeInventoryHashes.Count -ne 1 -or
    $sbomRuntimeInventoryHashes[0] -ne $runtimeInventoryHash) {
    throw 'SBOM does not identify the exact packaged runtime inventory hash.'
}
$sbomCompleteness = @($sbom.metadata.component.properties |
    Where-Object { $_.name -eq 'ufm:sbom-completeness' } |
    ForEach-Object { [string]$_.value })
if ($sbomCompleteness.Count -ne 1 -or $sbomCompleteness[0] -ne 'complete') {
    throw 'A public-release installer requires an explicitly complete SBOM.'
}
$licenseReview = @($sbom.metadata.component.properties |
    Where-Object { $_.name -eq 'ufm:license-review' } |
    ForEach-Object { [string]$_.value })
if ($licenseReview.Count -ne 1 -or $licenseReview[0] -ne 'approved' -or
    @($sbom.metadata.component.licenses).Count -eq 0) {
    throw 'A public-release installer requires an approved license review and declared project license in the SBOM.'
}
$compositionStates = @($sbom.compositions | ForEach-Object { [string]$_.aggregate })
if ($compositionStates.Count -ne 1 -or $compositionStates[0] -ne 'complete') {
    throw 'A public-release installer requires one complete CycloneDX composition.'
}
$bundleExecutable = Join-Path $bundlePath 'UFM Studio.exe'
$bundleSignature = Get-AuthenticodeSignature -LiteralPath $bundleExecutable
if ($bundleSignature.Status -ne 'Valid' -or
    $bundleSignature.SignerCertificate.Thumbprint -ne $requiredSignerThumbprint) {
    throw 'The bundled UFM Studio executable must have a valid signature from the requested release certificate.'
}
$setupExe = Join-Path $outputPath "UFM-Studio-Setup-$($manifest.version).exe"
if (Test-Path -LiteralPath $setupExe) {
    throw "Installer output already exists; choose a new output directory: $setupExe"
}

$previousBundleDir = $env:UFM_BUNDLE_DIR
$previousAppVersion = $env:UFM_APP_VERSION
$previousInstallerOutput = $env:UFM_INSTALLER_OUTPUT
try {
    $env:UFM_BUNDLE_DIR = $bundlePath
    $env:UFM_APP_VERSION = [string]$manifest.version
    $env:UFM_INSTALLER_OUTPUT = $outputPath
    New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
    & $CompilerPath /Qp $issPath
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed with exit code $LASTEXITCODE." }
    if (-not (Test-Path -LiteralPath $setupExe -PathType Leaf)) {
        throw "Inno Setup did not create expected output: $setupExe"
    }
    if ($SigningCertificateThumbprint) {
        & (Join-Path $PSScriptRoot 'sign_windows_artifact.ps1') `
            -Path $setupExe -CertificateThumbprint $SigningCertificateThumbprint `
            -TimestampServer $TimestampServer
        if ($LASTEXITCODE -ne 0) { throw 'Installer signing failed.' }
    }
    $installerSignature = Get-AuthenticodeSignature -LiteralPath $setupExe
    if ($installerSignature.Status -ne 'Valid' -or
        $installerSignature.SignerCertificate.Thumbprint -ne $requiredSignerThumbprint) {
        throw 'The public-release installer signature did not verify with the requested certificate.'
    }
    Write-Output "Built per-user installer: $setupExe"
}
finally {
    $env:UFM_BUNDLE_DIR = $previousBundleDir
    $env:UFM_APP_VERSION = $previousAppVersion
    $env:UFM_INSTALLER_OUTPUT = $previousInstallerOutput
}
