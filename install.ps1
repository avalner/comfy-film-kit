<#
.SYNOPSIS
    Installs comfy-film-kit for the agent runtimes on this machine.

.DESCRIPTION
    Links the skills in skills\ into the DeepSeek Harness and Codex skill folders as
    NTFS junctions (so the repository remains the single editable copy), creates the
    machine profile from its template, and reports everything it skipped.

    Nothing is overwritten unless -Force is passed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install.ps1

.EXAMPLE
    .\install.ps1 -ComfyRoot 'D:\ComfyUI_windows_portable' -Force
#>
[CmdletBinding()]
param(
    [string]$ToolsRoot,
    [string]$ComfyRoot = 'I:\Video Generation\ComfyUI_windows_portable',
    [string]$DshSkills,
    [string]$CodexSkills,
    [switch]$SkipCodex,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

if (-not $ToolsRoot) { $ToolsRoot = $PSScriptRoot }
if (-not $DshSkills) { $DshSkills = Join-Path $HOME '.dsh\skills' }
if (-not $CodexSkills) { $CodexSkills = Join-Path $HOME '.codex\skills' }

$ToolsRoot = (Resolve-Path $ToolsRoot).Path.TrimEnd('\')
$ComfyRoot = $ComfyRoot.TrimEnd('\')

$filmPy = Join-Path $ToolsRoot 'comfy-film\scripts\film.py'
if (-not (Test-Path $filmPy)) {
    throw "Not a comfy-film-kit checkout: $filmPy is missing."
}

$script:done = @()
$script:skipped = @()

function Write-TextFile([string]$Path, [string]$Text) {
    $dir = Split-Path $Path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

function New-SkillLink([string]$LinkPath, [string]$TargetPath, [string]$Label) {
    if (-not (Test-Path $TargetPath)) {
        $script:skipped += "$Label - target missing: $TargetPath"
        return
    }
    if (Test-Path $LinkPath) {
        $item = Get-Item $LinkPath -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
            $existing = ''
            try { $existing = $item.Target } catch { }
            if ($existing -and ($existing.TrimEnd('\') -ieq $TargetPath.TrimEnd('\'))) {
                $script:skipped += "$Label - already linked"
            }
            else {
                $script:skipped += "$Label - points somewhere else: $existing"
            }
            return
        }
        $script:skipped += "$Label - exists and is not a junction, left alone"
        return
    }
    New-Item -ItemType Directory -Force (Split-Path $LinkPath -Parent) | Out-Null
    New-Item -ItemType Junction -Path $LinkPath -Target $TargetPath | Out-Null
    $script:done += "$Label - linked"
}

Write-Host ''
Write-Host "comfy-film-kit"
Write-Host "  tools : $ToolsRoot"
Write-Host "  comfy : $ComfyRoot"
Write-Host ''

# ---------------------------------------------------------------- machine.json
$exampleMachine = Join-Path $ToolsRoot 'comfy-film\assets\machine.example.json'
$machinePath = Join-Path $ToolsRoot 'comfy-film\assets\machine.json'
if (Test-Path $machinePath) {
    if ($Force) {
        Write-Host 'machine.json exists - overwriting (-Force)'
    }
    else {
        $script:skipped += 'machine.json - exists (use -Force to regenerate)'
    }
}
if ((Test-Path $exampleMachine) -and ($Force -or -not (Test-Path $machinePath))) {
    $comfySlash = $ComfyRoot.Replace('\', '/')
    $toolsSlash = $ToolsRoot.Replace('\', '/')
    $text = Get-Content $exampleMachine -Raw -Encoding UTF8
    $text = $text.Replace('<COMFYUI_ROOT>', $comfySlash).Replace('<TOOLS_ROOT>', $toolsSlash)
    Write-TextFile $machinePath $text
    # The template points at a made-up FFmpeg; use the one this machine actually has.
    $ff = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
    if (-not $ff) {
        foreach ($candidate in @('C:\Program Files\Shotcut\ffmpeg.exe', 'C:\ffmpeg\bin\ffmpeg.exe')) {
            if (Test-Path $candidate) { $ff = $candidate; break }
        }
    }
    if ($ff) {
        $obj = Get-Content $machinePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $obj.ffmpeg = $ff.Replace('\', '/')
        $obj.ffprobe = ($ff -replace 'ffmpeg\.exe$', 'ffprobe.exe').Replace('\', '/')
        Write-TextFile $machinePath ($obj | ConvertTo-Json -Depth 8)
        $script:done += "machine.json - created for $ComfyRoot (ffmpeg: $ff)"
    }
    else {
        $script:done += "machine.json - created for $ComfyRoot"
        $script:skipped += 'ffmpeg not found - set ffmpeg and ffprobe in machine.json'
    }
}

# ---------------------------------------------------------------------- skills
$skillNames = @('comfy-film-dsh', 'living-paintings', 'h3-prompt-writing')
foreach ($name in $skillNames) {
    $target = Join-Path $ToolsRoot "skills\$name"
    if (Test-Path $target) {
        New-SkillLink (Join-Path $DshSkills $name) $target "dsh\$name"
    }
}

if (-not $SkipCodex) {
    foreach ($name in @('living-paintings', 'h3-prompt-writing')) {
        $target = Join-Path $ToolsRoot "skills\$name"
        if (Test-Path $target) {
            New-SkillLink (Join-Path $CodexSkills $name) $target "codex\$name"
        }
    }
}

# Codex needs its own folder: SKILL.md is a real file there, and script folders are links.
$codexSkill = Join-Path $CodexSkills 'comfy-film'
$codexMd = Join-Path $codexSkill 'SKILL.md'
$sourceMd = Join-Path $ToolsRoot 'skills\comfy-film\SKILL.md'
if (-not $SkipCodex) {
    if (-not (Test-Path $codexSkill)) {
        New-Item -ItemType Directory -Force $codexSkill | Out-Null
    }
    if ((Test-Path $sourceMd) -and ($Force -or -not (Test-Path $codexMd))) {
        Copy-Item $sourceMd $codexMd -Force
        $script:done += 'codex\comfy-film\SKILL.md - installed'
    }
    elseif (Test-Path $codexMd) {
        $script:skipped += 'codex\comfy-film\SKILL.md - exists (use -Force to refresh from the repo)'
    }
    New-SkillLink (Join-Path $codexSkill 'scripts') (Join-Path $ToolsRoot 'comfy-film\scripts') 'codex\comfy-film\scripts'
    New-SkillLink (Join-Path $codexSkill 'assets') (Join-Path $ToolsRoot 'comfy-film\assets') 'codex\comfy-film\assets'
}

# ------------------------------------------------------------------- paths.json
# The one file the skills resolve their paths from. The skill text is written against the author's
# machine; this file is what makes the same commands work on somebody else's.
$machinePath = Join-Path $ToolsRoot 'comfy-film\assets\machine.json'
$machine = $null
if (Test-Path $machinePath) { $machine = Get-Content $machinePath -Raw -Encoding UTF8 | ConvertFrom-Json }
$pythonPath = if ($machine -and $machine.python) { $machine.python } else { $ComfyRoot.Replace('\', '/') + '/python_embeded/python.exe' }
$ffmpegPath = if ($machine -and $machine.ffmpeg) { $machine.ffmpeg } else { 'ffmpeg' }
$ffprobePath = if ($machine -and $machine.ffprobe) { $machine.ffprobe } else { 'ffprobe' }
$paths = [ordered]@{
    tools   = $ToolsRoot.Replace('\', '/')
    comfy   = ($pythonPath -replace '/python_embeded/python\.exe$', '')
    python  = $pythonPath
    ffmpeg  = $ffmpegPath
    ffprobe = $ffprobePath
}
Write-TextFile (Join-Path $ToolsRoot 'paths.json') ($paths | ConvertTo-Json)
$script:done += 'paths.json - written (this is what the skills resolve against)'

# --------------------------------------------------------------------- summary
Write-Host ''
Write-Host 'Done:'
if ($script:done.Count -eq 0) { Write-Host '  (nothing)' } else { $script:done | ForEach-Object { Write-Host "  + $_" } }
Write-Host ''
Write-Host 'Skipped:'
if ($script:skipped.Count -eq 0) { Write-Host '  (nothing)' } else { $script:skipped | ForEach-Object { Write-Host "  = $_" } }
Write-Host ''
Write-Host 'Next: check the machine profile, then'
Write-Host "  & '$ComfyRoot\python_embeded\python.exe' '$ToolsRoot\comfy-film\scripts\film.py' doctor --project <project>"
Write-Host ''
Write-Host 'No ComfyUI or models yet? Check what is missing first (downloads nothing):'
Write-Host "  pwsh -File '$ToolsRoot\setup\install-comfy.ps1' -Modes video,long -Check"
Write-Host ''
