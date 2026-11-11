<#
.SYNOPSIS
    Installs the tools comfy-film-kit needs: ComfyUI, custom nodes, models and FFmpeg.

.DESCRIPTION
    One entry point for a machine that has nothing: a fresh Windows + NVIDIA card should end up
    able to run the same films this kit produces. Nothing is downloaded twice, nothing that is
    already present is touched, and every download resumes after a broken connection.

    Choose the modes you actually want — the model set is the union of their roles:

        video    short clip: first frame, or first + last frame (I2VA / FL2VA)
        long     scenes that continue each other (guide + last keyframe)
        refs     references: up to 9 pictures, reference video, audio
        lipsync  a character speaks/sings your audio track
        actor    dialogue scenes from a voice sample
        swap     replace a person in a video with a character from a picture
        action   action scenes: fight, chase, running
        krea, kreareal, qwen, flux    pictures: by text / realism / editing
        upscale, relayvsr            video and photo enlargement

    Run with -Check first: it reports what is present and downloads nothing.

.PARAMETER Modes
    Modes to install for. `all` selects every mode in the catalog.

.PARAMETER ComfyRoot
    The portable ComfyUI folder (the one that contains python_embeded). Defaults to an existing
    install, otherwise to the fixed drive with the most free space.

.PARAMETER Profile
    lite / standard / max — how heavy a video model to download. auto picks by VRAM + RAM.

.PARAMETER Check
    Report only. No downloads, no writes.

.EXAMPLE
    .\install-comfy.ps1 -Modes video,long -Check

.EXAMPLE
    .\install-comfy.ps1 -Modes video,long,refs,lipsync
#>
[CmdletBinding()]
param(
    [string[]]$Modes = @(),
    [string]$ComfyRoot = '',
    [ValidateSet('auto', 'lite', 'standard', 'max')][string]$Profile = 'auto',
    [ValidateSet('auto', 'int8', 'nvfp4')][string]$VideoModel = 'auto',
    [switch]$Check,
    [switch]$SkipNodes,
    [switch]$SkipFFmpeg,
    [switch]$Force,
    [int]$Retries = 20
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# `-File install-comfy.ps1 -Modes video,long` reaches us as one string: split it here so both
# `-Modes video,long` and `-Modes video long` work.
$Modes = @($Modes | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$ToolsRoot = (Resolve-Path (Split-Path $PSScriptRoot -Parent)).Path
$CatalogPath = Join-Path $PSScriptRoot 'catalog.json'
if (-not (Test-Path $CatalogPath)) { throw "catalog.json is missing next to this script." }
$cat = Get-Content $CatalogPath -Raw -Encoding UTF8 | ConvertFrom-Json

$script:result = [ordered]@{
    status = 'unknown'; comfy_root = ''; comfy_present = $false; python = ''; ffmpeg = ''
    gpu = ''; vram_gb = 0; driver = 0; ram_gb = 0; disk_free_gb = 0
    profile = ''; modes = @(); downloaded = @(); missing = @(); errors = @()
}

function Say([string]$Text) { Write-Host $Text }
function Head([string]$Text) { Write-Host ''; Write-Host $Text -ForegroundColor Cyan }

function Fail([string]$Text) {
    $script:result.status = 'error'
    $script:result.errors += $Text
    Say "ERROR: $Text"
    Say ('##RESULT## ' + ($script:result | ConvertTo-Json -Depth 6 -Compress))
    exit 1
}

# ------------------------------------------------------------------ hardware
function Get-Hardware {
    $hw = @{ nvidia = $false; gpu = ''; vram_gb = 0; compute_cap = 0; driver = 0; ram_gb = 0 }
    try {
        $out = & nvidia-smi --query-gpu=name,memory.total,compute_cap,driver_version --format=csv,noheader,nounits 2>$null
        $rows = @($out | Where-Object { $_.Trim() } | ForEach-Object { $_.Split(',') | ForEach-Object { $_.Trim() } })
        if ($rows.Count -ge 4) {
            # take the card with the most memory; rows are flattened groups of four
            $best = $null
            for ($i = 0; $i + 3 -lt $rows.Count; $i += 4) {
                $mem = [double]$rows[$i + 1]
                if (-not $best -or $mem -gt $best.mem) {
                    $best = @{ name = $rows[$i]; mem = $mem; cap = [double]$rows[$i + 2]; driver = [double]$rows[$i + 3] }
                }
            }
            if ($best) {
                $hw.nvidia = $true
                $hw.gpu = $best.name -replace '^NVIDIA GeForce ', ''
                $hw.vram_gb = [math]::Round($best.mem / 1024)
                $hw.compute_cap = $best.cap
                $hw.driver = $best.driver
            }
        }
    }
    catch { }
    try { $hw.ram_gb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB) } catch { }
    return $hw
}

function Get-FreeGB([string]$Path) {
    $p = $Path
    while ($p -and -not (Test-Path $p)) { $p = Split-Path $p -Parent }
    if (-not $p) { return 0 }
    try { return [math]::Round((Get-PSDrive -PSProvider FileSystem -Name ([System.IO.Path]::GetPathRoot($p).Substring(0, 1))).Free / 1GB) } catch { return 0 }
}

function Find-ComfyRoot {
    if ($ComfyRoot) { return $ComfyRoot }
    # 1. an install this kit already points at, and whose interpreter really exists
    $profilePath = Join-Path $ToolsRoot 'comfy-film\assets\machine.json'
    if (Test-Path $profilePath) {
        try {
            $knownPy = (Get-Content $profilePath -Raw -Encoding UTF8 | ConvertFrom-Json).python
            if ($knownPy -and (Test-Path $knownPy)) { return (Split-Path (Split-Path $knownPy -Parent) -Parent) }
        }
        catch { }
    }
    # 2. a portable ComfyUI next to the kit or one level up
    foreach ($candidate in @((Join-Path $ToolsRoot 'ComfyUI_windows_portable'),
                             (Join-Path (Split-Path $ToolsRoot -Parent) 'ComfyUI_windows_portable'))) {
        if (Test-Path (Join-Path $candidate 'python_embeded\python.exe')) { return $candidate }
    }
    # 3. the fixed drive with the most free space — the default the user is told about before installing
    $bestDrive, $bestFree = $null, 0
    foreach ($d in Get-PSDrive -PSProvider FileSystem) {
        if ($d.Free -and $d.Free -gt $bestFree) { $bestDrive = $d.Root; $bestFree = $d.Free }
    }
    if ($bestDrive -and $bestFree -gt 60GB) { return (Join-Path $bestDrive 'ComfyUI_windows_portable') }
    return (Join-Path $env:LOCALAPPDATA 'ComfyUI_windows_portable')
}

# ------------------------------------------------------------------ download
function Get-File([string]$Url, [string]$Dest, [long]$Size, [string]$Label) {
    $destDir = Split-Path $Dest -Parent
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Force $destDir | Out-Null }
    if (Test-Path $Dest) { Say ("  = {0} (already there)" -f $Label); return }
    $part = "$Dest.part"
    $curl = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
    if (-not $curl) { throw 'curl.exe is required (it ships with Windows 10 1803 and newer).' }
    for ($attempt = 1; $attempt -le $Retries; $attempt++) {
        $have = 0
        if (Test-Path $part) { $have = (Get-Item $part).Length }
        $curlArgs = @('-L', '--fail', '--silent', '--show-error', '--connect-timeout', '30',
                      '--retry', '3', '--retry-delay', '3', '-o', $part, $Url)
        if ($have -gt 0) { $curlArgs = @('-C', '-') + $curlArgs }
        $argLine = ($curlArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' '
        Say ("  > {0}  {1:N1} / {2:N1} GB" -f $Label, ($have / 1GB), ([math]::Max($Size, $have) / 1GB))
        $errFile = [System.IO.Path]::GetTempFileName()
        $outFile = [System.IO.Path]::GetTempFileName()
        $proc = Start-Process -FilePath $curl -ArgumentList $argLine -PassThru -WindowStyle Hidden `
            -RedirectStandardError $errFile -RedirectStandardOutput $outFile
        $last = -1
        while (-not $proc.HasExited) {
            Start-Sleep -Seconds 5
            $now = 0
            if (Test-Path $part) { $now = (Get-Item $part).Length }
            $pct = if ($Size -gt 0) { [int](100 * $now / $Size) } else { 0 }
            if ($now -ne $last) {
                Say ("    {0,6:N2} GB  {1,3}%" -f ($now / 1GB), $pct)
                $last = $now
            }
        }
        $proc.WaitForExit()
        if ($proc.ExitCode -eq 0 -and (Test-Path $part)) {
            Move-Item -Force $part $Dest
            Remove-Item $errFile, $outFile -Force -ErrorAction SilentlyContinue
            Say ("  + {0}" -f $Label)
            return
        }
        $why = ''
        if (Test-Path $errFile) { $why = (Get-Content $errFile -Raw -ErrorAction SilentlyContinue) -replace '\s+', ' ' }
        Remove-Item $errFile, $outFile -Force -ErrorAction SilentlyContinue
        Say ("  ! {0}: {1} (attempt {2}/{3})" -f $Label, $why.Trim(), $attempt, $Retries)
        if ($attempt -eq $Retries) { throw "Could not download $Label : $why" }
        Start-Sleep -Seconds ([math]::Min(30, 3 + 3 * $attempt))
    }
}

# ------------------------------------------------------------------ planning
function Resolve-Plan {
    param($Hw, [string[]]$ModeList)

    $all = @($cat.modes.PSObject.Properties.Name)
    if ($ModeList -contains 'all') { $ModeList = $all }
    if (-not $ModeList -or $ModeList.Count -eq 0) {
        Fail ("Nothing selected. Pass -Modes with the modes the user chose, e.g. -Modes video,long. Available: " + ($all -join ', '))
    }
    $unknown = @($ModeList | Where-Object { $all -notcontains $_ })
    if ($unknown.Count) {
        Fail ("Unknown mode(s): {0}. Available: {1}" -f ($unknown -join ', '), ($all -join ', '))
    }

    $profile = $Profile
    if ($profile -eq 'auto') {
        $vram = [double]$Hw.vram_gb; $ram = [double]$Hw.ram_gb
        if (($vram + $ram) -ge 48 -and $vram -ge 24) { $profile = 'max' }
        elseif (($vram + $ram) -ge 40) { $profile = 'standard' }
        else { $profile = 'lite' }
    }

    $choice = @{}
    foreach ($r in $cat.defaults.PSObject.Properties) { $choice[$r.Name] = $r.Value }
    foreach ($p in @('lipsync_unet', 'action_unet')) {
        $v = $cat.profiles.$profile.$p
        if ($v) { $choice[$p] = $v }
    }
    if ($VideoModel -ne 'auto') { $choice['fast_unet'] = $VideoModel }
    elseif ($Hw.compute_cap -ge 12 -and $Hw.vram_gb -ge 16) { $choice['fast_unet'] = 'nvfp4' }

    $roles = @{}
    foreach ($m in $ModeList) {
        foreach ($r in $cat.mode_roles.$m) { $roles[$r] = $true }
        $opt = $cat.mode_optional.$m
        if ($opt) { foreach ($r in $opt) { $roles[$r] = $true } }
    }

    # Only the node packs these modes actually use. A mode without a mapping gets everything.
    $packNames = @()
    $unmapped = @()
    foreach ($m in $ModeList) {
        $p = $cat.node_packs.$m
        if ($p) { $packNames += $p } else { $unmapped += $m }
    }
    if ($unmapped.Count) { $packNames += @($cat.nodes | ForEach-Object { $_.name }) }
    $packs = @($packNames | Sort-Object -Unique)

    $models = @()
    foreach ($roleName in $roles.Keys) {
        $roleDef = $cat.roles.PSObject.Properties[$roleName]
        if (-not $roleDef) { continue }
        $variantName = $choice[$roleName]
        if (-not $variantName) { $variantName = @($roleDef.Value.variants.PSObject.Properties.Name)[0] }
        $v = $roleDef.Value.variants.$variantName
        $models += [pscustomobject]@{
            role = $roleName; variant = $variantName; title = $roleDef.Value.title
            url = $v.url; size = [long]$v.size; category = $v.category; file = $v.file; name = $v.name
        }
    }
    return [pscustomobject]@{
        profile = $profile
        modes = @($ModeList)
        models = $models
        packs = $packs
        total = [long](($models | Measure-Object -Property size -Sum).Sum)
    }
}

function Get-ModelPath([string]$ModelRoot, $Model) {
    # catalog `name` is relative to the category folder: diffusion_models, text_encoders, vae, loras...
    $rel = ($Model.name -replace '\\', '/')
    return (Join-Path (Join-Path $ModelRoot $Model.category) ($rel -replace '/', '\'))
}

$script:index = @{}
function Get-ModelIndex([string]$ModelRoot, [string]$Category) {
    if ($script:index.ContainsKey($Category)) { return $script:index[$Category] }
    $map = @{}
    $dir = Join-Path $ModelRoot $Category
    if (Test-Path $dir) {
        Get-ChildItem $dir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            if (-not $map.ContainsKey($_.Name)) { $map[$_.Name] = $_.FullName }
        }
    }
    $script:index[$Category] = $map
    return $map
}

function Resolve-ModelFile([string]$ModelRoot, $Model) {
    # Prefer the category root (the controller addresses files by bare name), but accept an
    # existing copy in any subfolder so nothing is downloaded twice.
    $direct = Get-ModelPath $ModelRoot $Model
    if (Test-Path $direct) { return $direct }
    $idx = Get-ModelIndex $ModelRoot $Model.category
    $leafs = @($Model.file)
    $alt = $cat.aliases.PSObject.Properties[$Model.file]
    if ($alt) { $leafs += @($alt.Value) }
    foreach ($leaf in $leafs) {
        if ($leaf -and $idx.ContainsKey($leaf)) { return $idx[$leaf] }
    }
    return $direct
}

function Test-Present([string]$Path, [long]$Size) {
    if (-not (Test-Path $Path)) { return $false }
    $item = Get-Item $Path -ErrorAction SilentlyContinue
    if (-not $item -or $item.PSIsContainer) { return $false }
    if ($Size -le 0) { return $true }
    return (($item.Length -ge ($Size * 0.9)) -and ($item.Length -le ($Size * 1.2)))
}

# ------------------------------------------------------------------ install
function Install-Comfy {
    param([string]$Root)
    $py = Join-Path $Root 'python_embeded\python.exe'
    if (Test-Path $py) { Say "  = ComfyUI already installed: $Root"; return }
    if ($Check) { return }

    $installDir = Split-Path $Root -Parent
    if (-not (Test-Path $installDir)) { New-Item -ItemType Directory -Force $installDir | Out-Null }
    $archive = Join-Path $installDir 'downloads\ComfyUI_windows_portable_nvidia.7z'
    Get-File -Url $cat.comfy.url -Dest $archive -Size ([long]$cat.comfy.size) -Label ("ComfyUI {0} ({1:N1} GB)" -f $cat.comfy.version, ($cat.comfy.size / 1GB))

    $seven = Join-Path $installDir 'tools\7zr.exe'
    if (-not (Test-Path $seven)) {
        Get-File -Url 'https://github.com/ip7z/7zip/releases/latest/download/7zr.exe' -Dest $seven -Size 700000 -Label '7-Zip extractor'
    }
    Say '  extracting ComfyUI (a few minutes)'
    & $seven x -y "-o$installDir" $archive | Out-Null
    if (-not (Test-Path $py)) { throw "Extraction finished but $py is missing." }
    Remove-Item $archive -Force -ErrorAction SilentlyContinue
    Say '  + ComfyUI installed'
}

function Install-Nodes {
    param([string]$Root, [string[]]$Packs)
    $py = Join-Path $Root 'python_embeded\python.exe'
    $nodesDir = Join-Path $Root 'ComfyUI\custom_nodes'
    if (-not (Test-Path $nodesDir)) { New-Item -ItemType Directory -Force $nodesDir | Out-Null }
    $cache = Join-Path $Root 'cache'
    $env:PYTHONUTF8 = '1'

    foreach ($pack in $cat.nodes) {
        if ($Packs -and ($Packs -notcontains $pack.name)) { Say ("  - nodes: {0} (not needed for these modes)" -f $pack.name); continue }
        $target = Join-Path $nodesDir $pack.name
        if (Test-Path $target) { Say ("  = nodes: {0}" -f $pack.name); continue }
        if ($Check) { continue }
        $zipUrl = "https://github.com/$($pack.repo)/archive/$($pack.commit).zip"
        $zip = Join-Path ([System.IO.Path]::GetTempPath()) ("$($pack.name).zip")
        Say ("  > nodes: {0}" -f $pack.name)
        $ok = $false
        foreach ($url in @($zipUrl, "https://codeload.github.com/$($pack.repo)/zip/$($pack.commit)")) {
            try { Get-File -Url $url -Dest $zip -Size 0 -Label $pack.name; $ok = $true; break }
            catch { Say ("  ! {0}: retrying another address" -f $pack.name) }
        }
        if (-not $ok) { throw "Could not download node pack $($pack.name)" }

        $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("h3nodes-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force $tmp | Out-Null
        Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
        $top = Get-ChildItem $tmp -Directory | Select-Object -First 1
        Move-Item -Force $top.FullName $target
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item $zip -Force -ErrorAction SilentlyContinue

        $req = Join-Path $target 'requirements.txt'
        if (Test-Path $req) {
            if ((Get-Content $req -Raw).Trim()) {
                Say ("    pip install -r requirements.txt")
                $env:PIP_CACHE_DIR = Join-Path $cache 'pip'
                & $py -s -m pip install --disable-pip-version-check -q -r $req 2>&1 | ForEach-Object { "    $_" }
                if ($LASTEXITCODE -ne 0) { Say ("    ! pip failed for {0} (the node may still work)" -f $pack.name) }
            }
        }
        Say ("  + nodes: {0}" -f $pack.name)
    }
}

function Install-FFmpeg {
    param([string]$Root)
    $existing = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
    if (-not $existing) {
        foreach ($c in @('C:\Program Files\Shotcut\ffmpeg.exe', 'C:\ffmpeg\bin\ffmpeg.exe', "$Root\ffmpeg\bin\ffmpeg.exe")) {
            if (Test-Path $c) { $existing = $c; break }
        }
    }
    if ($existing) { Say "  = FFmpeg: $existing"; return $existing }
    if ($Check -or $SkipFFmpeg) { return '' }

    $installDir = Split-Path $Root -Parent
    $zip = Join-Path $installDir 'downloads\ffmpeg.zip'
    Get-File -Url 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -Dest $zip -Size 90000000 -Label 'FFmpeg'
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("ffmpeg-" + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force
    $bin = Get-ChildItem $tmp -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1
    if (-not $bin) { throw 'FFmpeg archive has no ffmpeg.exe' }
    $dest = Join-Path $installDir 'ffmpeg\bin'
    New-Item -ItemType Directory -Force $dest | Out-Null
    Copy-Item (Join-Path $bin.DirectoryName '*') $dest -Force
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Say "  + FFmpeg: $dest"
    return (Join-Path $dest 'ffmpeg.exe')
}

function Write-Machine([string]$Root, [string]$FFmpeg) {
    $assets = Join-Path $ToolsRoot 'comfy-film\assets'
    $example = Join-Path $assets 'machine.example.json'
    $target = Join-Path $assets 'machine.json'
    if (Test-Path $target) {
        # A profile that points at a vanished interpreter is worse than none: rewrite it.
        $stale = $false
        try {
            $oldPy = (Get-Content $target -Raw -Encoding UTF8 | ConvertFrom-Json).python
            $stale = -not ($oldPy -and (Test-Path $oldPy))
        }
        catch { $stale = $true }
        if ($stale) { Say '  ! machine.json points at a missing interpreter: rewriting it' }
        elseif (-not $Force) { Say "  = machine.json already exists (use -Force to rewrite)"; return }
    }
    $comfySlash = $Root.Replace('\', '/')
    $toolsSlash = $ToolsRoot.Replace('\', '/')
    $text = (Get-Content $example -Raw -Encoding UTF8).Replace('<COMFYUI_ROOT>', $comfySlash).Replace('<TOOLS_ROOT>', $toolsSlash)
    if ($FFmpeg) {
        $ffSlash = $FFmpeg.Replace('\', '/')
        $probe = $ffSlash -replace 'ffmpeg\.exe$', 'ffprobe.exe'
        $obj = $text | ConvertFrom-Json
        $obj.ffmpeg = $ffSlash
        $obj.ffprobe = $probe
        $text = $obj | ConvertTo-Json -Depth 8
    }
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($target, $text, $utf8)
    Say "  + machine.json written"
}

# ---------------------------------------------------------------------- main
Head 'comfy-film-kit installer'

$hw = Get-Hardware
$root = Find-ComfyRoot
$modelRoot = Join-Path $root 'ComfyUI\models'
$py = Join-Path $root 'python_embeded\python.exe'

$script:result.gpu = $hw.gpu
$script:result.vram_gb = $hw.vram_gb
$script:result.driver = $hw.driver
$script:result.ram_gb = $hw.ram_gb
$script:result.comfy_root = $root
$script:result.python = $py
$script:result.disk_free_gb = Get-FreeGB (Split-Path $root -Parent)

Say ("  GPU:    {0} ({1} GB), driver {2}" -f ($(if ($hw.gpu) { $hw.gpu } else { 'not found' })), $hw.vram_gb, $hw.driver)
Say ("  RAM:    {0} GB, disk free: {1} GB" -f $hw.ram_gb, $script:result.disk_free_gb)
Say ("  ComfyUI: {0}" -f $root)

if (-not $hw.nvidia) { Say '  ! No NVIDIA GPU found. ComfyUI will install, but generation needs one.' }
elseif ($hw.driver -gt 0 -and $hw.driver -lt [double]$cat.min_driver) {
    Say ("  ! Driver {0} is older than {1}: the bundled PyTorch needs a newer one." -f $hw.driver, $cat.min_driver)
}

$plan = Resolve-Plan -Hw $hw -ModeList $Modes
$script:result.profile = $plan.profile
$script:result.modes = $plan.modes
$script:result | Add-Member -NotePropertyName node_packs -NotePropertyValue $plan.packs -Force
Say ("  Modes:  {0}  (profile: {1})" -f ($plan.modes -join ', '), $plan.profile)
Say ("  Nodes:  {0}" -f ($plan.packs -join ', '))
Say ("  Models: {0} files, {1:N1} GB" -f $plan.models.Count, ($plan.total / 1GB))

if ($script:result.disk_free_gb -gt 0 -and $script:result.disk_free_gb -lt [math]::Ceiling($plan.total / 1GB)) {
    Say ("  ! Only {0} GB free for {1:N1} GB of models." -f $script:result.disk_free_gb, ($plan.total / 1GB))
}

Head '1/4 ComfyUI'
Install-Comfy -Root $root

Head '2/4 custom nodes'
if ($SkipNodes) { Say '  - skipped' } else { Install-Nodes -Root $root -Packs $plan.packs }

Head '3/4 models'
foreach ($m in $plan.models) {
    $path = Resolve-ModelFile $modelRoot $m
    if (Test-Present $path ([long]$m.size)) { Say ("  = {0} — {1}" -f $m.title, $m.file); continue }
    if ($Check) { $script:result.missing += $m.file; continue }
    Say ("  > {0} — {1} ({2:N1} GB)" -f $m.title, $m.file, ($m.size / 1GB))
    Get-File -Url $m.url -Dest $path -Size ([long]$m.size) -Label $m.file
    $script:result.downloaded += $m.file
}

Head '4/4 FFmpeg'
$ffmpeg = Install-FFmpeg -Root $root
if ($ffmpeg) { $script:result.ffmpeg = $ffmpeg }

$script:result.comfy_present = Test-Path $py
if (-not $Check -and $script:result.comfy_present) {
    # cache and temp stay inside the install folder instead of the Windows profile
    $cache = Join-Path $root 'cache'
    foreach ($sub in @('pip', 'huggingface', 'torch', 'temp')) { New-Item -ItemType Directory -Force (Join-Path $cache $sub) | Out-Null }
    Write-Machine -Root $root -FFmpeg $ffmpeg
}

$modelsLeft = @($plan.models | Where-Object { -not (Test-Present (Resolve-ModelFile $modelRoot $_) ([long]$_.size)) })
$script:result.missing = @($modelsLeft | ForEach-Object { $_.file })
if (-not $ffmpeg) { Say '  ! FFmpeg not found: trim, stitch and finalize need ffmpeg/ffprobe in machine.json.' }

if ($Check) {
    if ($script:result.missing.Count -eq 0 -and $script:result.comfy_present) { $script:result.status = 'ready' }
    else { $script:result.status = 'missing' }
}
else { $script:result.status = 'installed' }

Head 'summary'
Say ("  ComfyUI: {0}" -f ($(if ($script:result.comfy_present) { 'ok' } else { 'MISSING' })))
Say ("  Models:  {0} present, {1} missing" -f ($plan.models.Count - $script:result.missing.Count), $script:result.missing.Count)
foreach ($m in $script:result.missing) { Say ("    - {0}" -f $m) }

Say ('##RESULT## ' + ($script:result | ConvertTo-Json -Depth 6 -Compress))
