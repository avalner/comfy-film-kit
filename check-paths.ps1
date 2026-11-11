<#
.SYNOPSIS
    Fails when an absolute path creeps back into the skill text.

.DESCRIPTION
    The skills are portable because they use variables ($Tools, $Comfy, $py, $Films, $Series,
    $Paintings, $MediaRoot) resolved from paths.json. A literal D:\..., C:\Users\... or a
    Codex-runtime interpreter in the text breaks that on every other machine, quietly — the command
    just fails on a missing file.

    Run it before committing, or let CI run it on every push.

.PARAMETER Path
    What to scan. Defaults to the skills folder next to this script.

.EXAMPLE
    .\check-paths.ps1
#>
[CmdletBinding()]
param(
    [string]$Path
)

$ErrorActionPreference = 'Stop'

$root = if ($Path) { (Resolve-Path $Path).Path } else { Join-Path $PSScriptRoot 'skills' }
if (-not (Test-Path $root)) { throw "Nothing to scan: $root is missing" }

# A drive letter in prose or in a command; http:// and friends are excluded by requiring an uppercase
# letter right before the colon.
$patterns = [ordered]@{
    'drive path'      = '\b[A-Z]:[\\/]'
    'codex runtime'   = 'codex-runtimes'
    'user profile'    = 'Users[\\/][A-Za-z0-9._-]+[\\/]'
    'google creds'    = 'Documents[\\/]Google'
}

$hits = @()
foreach ($file in Get-ChildItem $root -Recurse -File -Include '*.md', '*.txt') {
    $lineNumber = 0
    foreach ($line in Get-Content $file.FullName) {
        $lineNumber++
        foreach ($name in $patterns.Keys) {
            if ($line -match $patterns[$name]) {
                $hits += [pscustomobject]@{
                    Kind = $name
                    File = $file.FullName.Substring($root.Length).TrimStart('\')
                    Line = $lineNumber
                    Text = $line.Trim()
                }
                break
            }
        }
    }
}

if ($hits.Count -eq 0) {
    Write-Host "check-paths: clean ($root)"
    exit 0
}

Write-Host "check-paths: $($hits.Count) absolute path(s) in the skill text" -ForegroundColor Red
$hits | ForEach-Object {
    Write-Host ("  {0}:{1}  [{2}]  {3}" -f $_.File, $_.Line, $_.Kind, $_.Text)
}
Write-Host ''
Write-Host 'Replace them with $Tools / $Comfy / $py / $Films / $Series / $Paintings / $MediaRoot,'
Write-Host 'or with <placeholders>, and resolve them from paths.json (see the Paths section of the skill).'
exit 1
