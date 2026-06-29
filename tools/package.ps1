# Packages Ambient Symphony into a distributable Vintage Story mod zip.
# Layout inside the zip: modinfo.json + AmbientSymphony.dll + modicon.png + assets/ at the root.
# Entry names use FORWARD slashes (the ZIP spec + what Vintage Story's asset loader expects);
# PowerShell's Compress-Archive writes backslashes, so we build the archive by hand.
#
# Usage:
#   pwsh tools/package.ps1                 # version taken from src/modinfo.json
#   pwsh tools/package.ps1 -Version 1.0.2  # override the version in the zip filename
[CmdletBinding()]
param(
    [string]$Version
)
$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent $PSScriptRoot
$dll      = Join-Path $root 'src\bin\Release\AmbientSymphony.dll'
$modinfo  = Join-Path $root 'src\modinfo.json'
$modicon  = Join-Path $root 'media\modicon.png'
$assets   = Join-Path $root 'assets'
$buildDir = Join-Path $root 'build'

if (-not (Test-Path $dll))     { throw "Missing build output: $dll (run: dotnet build src/AmbientSymphony.csproj -c Release)" }
if (-not (Test-Path $modinfo)) { throw "Missing modinfo.json: $modinfo" }
if (-not (Test-Path $assets))  { throw "Missing assets folder: $assets" }
if (-not (Test-Path $modicon)) { throw "Missing modicon.png: $modicon (run: python tools/gen_cover.py)" }

# Default the version to whatever modinfo.json declares, so the zip name stays in sync.
if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = (Get-Content $modinfo -Raw | ConvertFrom-Json).version
}
if ([string]::IsNullOrWhiteSpace($Version)) { throw "Could not determine version (pass -Version or set it in modinfo.json)" }

$zip = Join-Path $buildDir "AmbientSymphony_$Version.zip"

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
if (Test-Path $zip) { Remove-Item -Force $zip }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

# (absolute source path, forward-slash entry name)
$items = New-Object System.Collections.Generic.List[object]
$items.Add(@($modinfo, 'modinfo.json'))
$items.Add(@($dll, 'AmbientSymphony.dll'))
$items.Add(@($modicon, 'modicon.png'))

$assetsParent = (Split-Path -Parent $assets)
Get-ChildItem -Path $assets -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($assetsParent.Length + 1) -replace '\\', '/'
    $items.Add(@($_.FullName, $rel))
}

$archive = [System.IO.Compression.ZipFile]::Open($zip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($it in $items) {
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archive, $it[0], $it[1], [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
    }
}
finally {
    $archive.Dispose()
}

# Read back the entry count, disposing the handle so the file is never left locked.
$verify = [System.IO.Compression.ZipFile]::OpenRead($zip)
try { $count = $verify.Entries.Count } finally { $verify.Dispose() }

$size = [math]::Round((Get-Item $zip).Length / 1KB, 0)
Write-Host "Packaged $zip ($size KB, $count entries, forward-slash paths)"
