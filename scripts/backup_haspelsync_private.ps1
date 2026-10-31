#requires -Version 7.2
param([string]$VerifyBundle)

# Secrets are zipped and restored for verification only in memory. DPAPI binds
# recovery to this Windows account. Nothing is copied into the distributable.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security.Cryptography.ProtectedData
Add-Type -AssemblyName System.IO.Compression
$projectRoot = Split-Path -Parent $PSScriptRoot
$scope = [System.Security.Cryptography.DataProtectionScope]::CurrentUser
$entropy = [System.Text.Encoding]::UTF8.GetBytes('UFM private HaspelSync backup v1')

function Get-HashBytes([byte[]]$Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { return [Convert]::ToHexString($sha.ComputeHash($Bytes)).ToLowerInvariant() }
    finally { $sha.Dispose() }
}

function Test-PrivateBundle([string]$Path) {
    $plain = $null
    try {
        $encrypted = [IO.File]::ReadAllBytes($Path)
        $plain = [Security.Cryptography.ProtectedData]::Unprotect($encrypted, $entropy, $scope)
        $memory = [IO.MemoryStream]::new($plain, $false)
        try {
            $zip = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Read)
            try {
                $reader = [IO.StreamReader]::new($zip.GetEntry('manifest.json').Open())
                try { $manifest = $reader.ReadToEnd() | ConvertFrom-Json }
                finally { $reader.Dispose() }
                if ($manifest.format -ne 1 -or $zip.Entries.Count -ne ($manifest.files.Count + 1)) {
                    throw 'Private archive manifest mismatch'
                }
                $seen = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
                foreach ($record in $manifest.files) {
                    if (-not $seen.Add($record.path)) { throw 'Duplicate archive member' }
                    $member = $zip.GetEntry($record.path)
                    if ($null -eq $member) { throw 'Missing archive member' }
                    $stream = $member.Open()
                    $copy = [IO.MemoryStream]::new()
                    try {
                        $stream.CopyTo($copy)
                        $bytes = $copy.ToArray()
                        try {
                            if ($bytes.Length -ne $record.bytes -or (Get-HashBytes $bytes) -ne $record.sha256) {
                                throw 'Restored content verification failed'
                            }
                        } finally { [Array]::Clear($bytes, 0, $bytes.Length) }
                    } finally { $stream.Dispose(); $copy.Dispose() }
                }
                return $manifest.files.Count
            } finally { $zip.Dispose() }
        } finally { $memory.Dispose() }
    } finally { if ($null -ne $plain) { [Array]::Clear($plain, 0, $plain.Length) } }
}

if ($VerifyBundle) {
    $verifiedCount = Test-PrivateBundle $VerifyBundle
    @{ verified = $true; files = $verifiedCount; plaintext_written = $false } | ConvertTo-Json -Compress
    exit 0
}

$sources = @(
    @{ label = 'legacy-runtime'; root = 'D:/Filament_Manager/haspelsync' },
    @{ label = 'own-runtime'; root = (Join-Path $projectRoot 'linked-stack/haspelsync') }
)
$inputs = [Collections.Generic.List[object]]::new()
foreach ($source in $sources) {
    foreach ($folder in @('printers', 'logs')) {
        $root = Join-Path $source.root $folder
        if (Test-Path -LiteralPath $root) {
            foreach ($file in (Get-ChildItem -LiteralPath $root -Recurse -File)) {
                if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Linked source rejected' }
                $relative = [IO.Path]::GetRelativePath($source.root, $file.FullName).Replace('\', '/')
                $inputs.Add(@{ source = $file.FullName; path = "$($source.label)/$relative" })
            }
        }
    }
    $environmentFile = Join-Path $source.root '.env'
    if (Test-Path -LiteralPath $environmentFile -PathType Leaf) {
        $inputs.Add(@{ source = $environmentFile; path = "$($source.label)/.env" })
    }
}
$inputs.Add(@{ source = 'D:/Filament_Manager/compose.yaml'; path = 'legacy-compose.yaml' })
$sharedEnvironment = 'D:/Filament_Manager/.env'
if (Test-Path -LiteralPath $sharedEnvironment -PathType Leaf) {
    $inputs.Add(@{ source = $sharedEnvironment; path = 'legacy-shared.env' })
}
$manifest = @{ format = 1; created_utc = [DateTime]::UtcNow.ToString('o'); files = @() }
$memory = [IO.MemoryStream]::new()
try {
    $zip = [IO.Compression.ZipArchive]::new($memory, [IO.Compression.ZipArchiveMode]::Create, $true)
    try {
        foreach ($inputFile in $inputs) {
            $bytes = [IO.File]::ReadAllBytes($inputFile.source)
            try {
                $entry = $zip.CreateEntry($inputFile.path)
                $stream = $entry.Open()
                try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
                $manifest.files += @{ path = $inputFile.path; bytes = $bytes.Length; sha256 = (Get-HashBytes $bytes) }
            } finally { [Array]::Clear($bytes, 0, $bytes.Length) }
        }
        # Reject the entire capture if any file changed during the capture.
        for ($index = 0; $index -lt $inputs.Count; $index++) {
            $current = [IO.File]::ReadAllBytes($inputs[$index].source)
            try {
                if ((Get-HashBytes $current) -ne $manifest.files[$index].sha256) {
                    throw 'Runtime changed during capture; retry a new snapshot'
                }
            } finally { [Array]::Clear($current, 0, $current.Length) }
        }
        $writer = [IO.StreamWriter]::new($zip.CreateEntry('manifest.json').Open())
        try { $writer.Write(($manifest | ConvertTo-Json -Depth 6)) } finally { $writer.Dispose() }
    } finally { $zip.Dispose() }
    $plain = $memory.ToArray()
    try { $cipher = [Security.Cryptography.ProtectedData]::Protect($plain, $entropy, $scope) }
    finally { [Array]::Clear($plain, 0, $plain.Length) }
} finally { $memory.Dispose() }

$run = Join-Path $projectRoot ('.runtime/private-haspelsync/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ'))
[IO.Directory]::CreateDirectory($run) | Out-Null
$target = Join-Path $run 'runtime.zip.dpapi'
$output = [IO.File]::Open($target, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write)
try { $output.Write($cipher, 0, $cipher.Length) } finally { $output.Dispose() }
$verifiedCount = Test-PrivateBundle $target
$publicReport = @{
    format = 1; created_utc = $manifest.created_utc; protection = 'DPAPI CurrentUser'
    encrypted_sha256 = (Get-HashBytes $cipher); files = $verifiedCount
    restored_in_memory = $true; plaintext_written = $false
    limitation = 'Requires original Windows user profile/DPAPI keys; not a portable backup'
}
$publicReport | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $run 'verification.json') -Encoding utf8
@{ run = $run; verified = $true; files = $verifiedCount; plaintext_written = $false } | ConvertTo-Json -Compress
