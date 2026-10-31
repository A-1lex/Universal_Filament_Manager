param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$CertificateThumbprint,
    [Parameter(Mandatory = $true)][string]$TimestampServer,
    [string]$SignToolPath
)

$ErrorActionPreference = 'Stop'
$artifactPath = [IO.Path]::GetFullPath($Path)
if (-not (Test-Path -LiteralPath $artifactPath -PathType Leaf)) {
    throw "Signing target is not a file: $artifactPath"
}
$thumbprint = ($CertificateThumbprint -replace '\s', '').ToUpperInvariant()
if ($thumbprint -notmatch '^[0-9A-F]{40}$') {
    throw 'CertificateThumbprint must be one SHA-1 certificate thumbprint.'
}
$timestampUri = $null
if (-not [Uri]::TryCreate($TimestampServer, [UriKind]::Absolute, [ref]$timestampUri) -or
    $timestampUri.Scheme -notin @('http', 'https') -or -not $timestampUri.Host) {
    throw 'TimestampServer must be an absolute HTTP(S) timestamp URL.'
}

$certificates = @(
    Get-ChildItem -LiteralPath Cert:\CurrentUser\My -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath Cert:\LocalMachine\My -ErrorAction SilentlyContinue
) | Where-Object { $_.Thumbprint -eq $thumbprint }
if ($certificates.Count -ne 1) {
    throw 'The exact signing certificate must exist in exactly one current-user or local-machine personal store.'
}
$certificate = $certificates[0]
if (-not $certificate.HasPrivateKey -or $certificate.NotBefore -gt (Get-Date) -or
    $certificate.NotAfter -le (Get-Date)) {
    throw 'The signing certificate must be currently valid and have an accessible private key.'
}
$codeSigningOid = '1.3.6.1.5.5.7.3.3'
if ($codeSigningOid -notin @($certificate.EnhancedKeyUsageList | ForEach-Object {
            $_.ObjectId.Value
        })) {
    throw 'The selected certificate does not have the Code Signing EKU.'
}

if (-not $SignToolPath) {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) { $SignToolPath = $command.Source }
}
if (-not $SignToolPath) {
    $kitsRoot = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    if (Test-Path -LiteralPath $kitsRoot -PathType Container) {
        $SignToolPath = Get-ChildItem -LiteralPath $kitsRoot -Filter signtool.exe -File -Recurse |
            Where-Object { $_.Directory.Name -eq 'x64' } |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $SignToolPath -or -not (Test-Path -LiteralPath $SignToolPath -PathType Leaf)) {
    throw 'Windows SDK signtool.exe was not found; install the Windows SDK or pass SignToolPath.'
}
$toolSignature = Get-AuthenticodeSignature -LiteralPath $SignToolPath
if ($toolSignature.Status -ne 'Valid' -or
    $toolSignature.SignerCertificate.Subject -notmatch '(^|,\s*)O=Microsoft Corporation(,|$)') {
    throw 'The selected signtool executable must have a valid Microsoft Corporation signature.'
}

& $SignToolPath sign /fd SHA256 /td SHA256 /tr $TimestampServer /sha1 $thumbprint $artifactPath
if ($LASTEXITCODE -ne 0) { throw "signtool signing failed with exit code $LASTEXITCODE." }
& $SignToolPath verify /pa /all /v $artifactPath
if ($LASTEXITCODE -ne 0) { throw "Authenticode verification failed with exit code $LASTEXITCODE." }
Write-Output "Signed and verified: $artifactPath"
