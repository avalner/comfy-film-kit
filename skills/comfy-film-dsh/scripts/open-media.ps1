# Open a media file for the user without relying on Windows file associations.
# Usage:  .\open-media.ps1 'I:\Path\file.png'   |   .\open-media.ps1 'I:\Path\clip.mp4'
# Why: this machine's per-user associations for .mp4 point at a UWP app and for .png at
# WPS Office; when those registrations go stale Windows shows a "How do you want to open
# this file?" dialog instead of the picture. Edge is always present and renders both PNG
# and H.264 MP4, so we call it explicitly with a file:// URI.

param(
    [Parameter(Mandatory = $true)][string]$Path,
    [switch]$Quiet
)

if (-not (Test-Path -LiteralPath $Path)) {
    Write-Error "File not found: $Path"
    exit 1
}

$resolved = (Resolve-Path -LiteralPath $Path).Path
$uri = (New-Object System.Uri $resolved).AbsoluteUri

$edge = @(
    'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
    'C:\Program Files\Microsoft\Edge\Application\msedge.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $edge) {
    Write-Error "Microsoft Edge not found; open the file manually: $uri"
    exit 2
}

Start-Process $edge -ArgumentList '--new-window', $uri
if (-not $Quiet) { "opened: $uri" }
