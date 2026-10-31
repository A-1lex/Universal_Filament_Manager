param(
    [string]$Destination = (Join-Path $PSScriptRoot '..\.runtime\node-v24.22.1-win-x64')
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$destinationPath = [IO.Path]::GetFullPath($Destination)
$runtimeBase = [IO.Path]::GetFullPath((Join-Path $projectRoot '.runtime'))
if (-not $destinationPath.StartsWith($runtimeBase, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Node runtime destination must stay under this project .runtime directory.'
}

$version = '24.22.1'
$archiveName = "node-v$version-win-x64.zip"
$archiveUrl = "https://nodejs.org/dist/v$version/$archiveName"
$archiveSha256 = 'd2046d28c2c3dcd211ac5145c0bf30e2047ef9dfb306693c8c6e2eccd8b95fa5'
$nodeSha256 = 'd702daa815eabbff763c7d3808e235cf031cf2ca70211b56847bc72f51e240e5'
$cachePath = Join-Path $runtimeBase 'downloads'
$archivePath = Join-Path $cachePath $archiveName
$nodePath = Join-Path $destinationPath 'node.exe'
$licensePath = Join-Path $destinationPath 'LICENSE'

New-Item -ItemType Directory -Path $cachePath -Force | Out-Null
New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null

if (-not (Test-Path -LiteralPath $archivePath -PathType Leaf)) {
    Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath
}
$actualArchiveHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualArchiveHash -ne $archiveSha256) {
    throw "Official Node archive SHA-256 mismatch: $actualArchiveHash"
}

if (-not (Test-Path -LiteralPath $nodePath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $licensePath -PathType Leaf)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
    try {
        foreach ($relative in @("node-v$version-win-x64/node.exe", "node-v$version-win-x64/LICENSE")) {
            $entry = $zip.GetEntry($relative)
            if (-not $entry) { throw "Node archive is missing $relative" }
            $leaf = [IO.Path]::GetFileName($relative)
            $target = Join-Path $destinationPath $leaf
            if (Test-Path -LiteralPath $target) {
                throw "Refusing to overwrite existing Node runtime file: $target"
            }
            $input = $entry.Open()
            try {
                $output = [IO.File]::Create($target)
                try { $input.CopyTo($output) } finally { $output.Dispose() }
            }
            finally { $input.Dispose() }
        }
    }
    finally { $zip.Dispose() }
}

$actualNodeHash = (Get-FileHash -LiteralPath $nodePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualNodeHash -ne $nodeSha256) {
    throw "Official Node executable SHA-256 mismatch: $actualNodeHash"
}
if (-not (Test-Path -LiteralPath $licensePath -PathType Leaf)) {
    throw 'Official Node LICENSE was not extracted.'
}
$reportedVersion = (& $nodePath --version).Trim()
if ($LASTEXITCODE -ne 0 -or $reportedVersion -ne "v$version") {
    throw "Unexpected Node runtime version: $reportedVersion"
}
Write-Output "Prepared official Node.js $reportedVersion; archive and executable SHA-256 verified."
