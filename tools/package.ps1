# Packages Ambient Symphony into a distributable Vintage Story mod zip.
# Layout inside the zip: modinfo.json + AmbientSymphony.dll + assets/ at the root.
# Entry names use FORWARD slashes (the ZIP spec + what Vintage Story's asset loader expects);
# PowerShell's Compress-Archive writes backslashes, so we build the archive by hand.
$ErrorActionPreference = 'Stop'

$root     = Split-Path -Parent $PSScriptRoot
$dll      = Join-Path $root 'src\bin\Release\AmbientSymphony.dll'
$modinfo  = Join-Path $root 'src\modinfo.json'
$assets   = Join-Path $root 'assets'
$buildDir = Join-Path $root 'build'
$zip      = Join-Path $buildDir 'AmbientSymphony_1.0.0.zip'

if (-not (Test-Path $dll))     { throw "Missing build output: $dll (run: dotnet build src/AmbientSymphony.csproj -c Release)" }
if (-not (Test-Path $modinfo)) { throw "Missing modinfo.json: $modinfo" }
if (-not (Test-Path $assets))  { throw "Missing assets folder: $assets" }

New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
if (Test-Path $zip) { Remove-Item -Force $zip }

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

# (absolute source path, forward-slash entry name)
$items = New-Object System.Collections.Generic.List[object]
$items.Add(@($modinfo, 'modinfo.json'))
$items.Add(@($dll, 'AmbientSymphony.dll'))

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

$size = [math]::Round((Get-Item $zip).Length / 1KB, 0)
$count = ([System.IO.Compression.ZipFile]::OpenRead($zip).Entries).Count
Write-Host "Packaged $zip ($size KB, $count entries, forward-slash paths)"
