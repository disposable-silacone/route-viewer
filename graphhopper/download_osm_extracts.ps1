# Download Geofabrik OSM extracts for GraphHopper (PA, NY, NJ, FL).
# Run from repo root:  .\graphhopper\download_osm_extracts.ps1

$ErrorActionPreference = "Stop"

$baseUrl = "https://download.geofabrik.de/north-america/us"
$dest = Join-Path $PSScriptRoot "pbf"

if (-not (Test-Path $dest)) {
    New-Item -ItemType Directory -Path $dest | Out-Null
}

$files = @(
    "pennsylvania-latest.osm.pbf",
    "new-york-latest.osm.pbf",
    "new-jersey-latest.osm.pbf",
    "florida-latest.osm.pbf"
)

foreach ($name in $files) {
    $out = Join-Path $dest $name
    if (Test-Path $out) {
        Write-Host "Skip (exists): $name"
        continue
    }
    $url = "$baseUrl/$name"
    Write-Host "Downloading $name ..."
    Invoke-WebRequest -Uri $url -OutFile $out
    Write-Host "  -> $out"
}

Write-Host ""
Write-Host "Done. Files in: $dest"
Write-Host "Start GraphHopper from graphhopper/ after placing map-matching.jar."
