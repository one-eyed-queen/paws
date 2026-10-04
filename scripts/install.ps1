# paws installer for windows. no admin, nothing outside ur user folder.
#
#   git clone https://github.com/one-eyed-queen/paws; cd paws; powershell -ExecutionPolicy Bypass -File scripts\install.ps1
#
# makes a private python env in %LOCALAPPDATA%\paws\venv, installs paws in it, puts its Scripts folder on
# your PATH and adds paws to the start menu. keep the folder u cloned, `paws update` pulls new versions from it.
# SLSsteam's config is %AppData%\SLSsteam\config.yaml, paws' own stuff goes in %AppData%\paws.
#
# options: -DryRun  -NoDesktop  -NoAlias  -Riced  -Minimal  -Prefix DIR  -Python PATH  -Help
# the look: -Riced is the full thing, -Minimal is plain text and leaves out the pictures, art, mini games and pillow.
param(
    [switch]$DryRun,
    [switch]$NoDesktop,
    [switch]$NoAlias,
    [switch]$Riced,
    [switch]$Minimal,
    [string]$Prefix = (Join-Path $env:LOCALAPPDATA "paws"),
    [string]$Python = "",
    [switch]$Help
)
$ErrorActionPreference = "Stop"

function Say($text) { Write-Host $text }
function Die($text) { Write-Host "paws installer: $text" -ForegroundColor Red; exit 1 }
function Run([string]$exe, [string[]]$arguments) {
    if ($DryRun) { Say "  would run: $exe $($arguments -join ' ')"; return }
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Die "$exe failed (exit code $LASTEXITCODE)" }
}

if ($Help) { Get-Content $PSCommandPath | Select-Object -Skip 1 -First 9 | ForEach-Object { $_ -replace '^# ?', '' }; exit 0 }

$Src = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $Src "pyproject.toml"))) { Die "run this from a paws checkout ($Src has no pyproject.toml)" }

# ---- a python that's new enough (3.10+) -------------------------------------------------------------
function PyOk($cmd, $extra) {
    try { & $cmd @extra -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null; return $LASTEXITCODE -eq 0 } catch { return $false }
}
$PyArgs = @()
if (-not $Python) {
    # the py launcher knows every python on the machine; plain `python` may be the microsoft store stub
    if ((Get-Command py -ErrorAction SilentlyContinue) -and (PyOk "py" @("-3"))) { $Python = "py"; $PyArgs = @("-3") }
    elseif ((Get-Command python -ErrorAction SilentlyContinue) -and (PyOk "python" @())) { $Python = "python" }
}
if (-not $Python) { Die "need python 3.10 or newer: winget install Python.Python.3.12 (then open a new terminal)" }
if (-not (PyOk $Python $PyArgs)) { Die "$Python is older than 3.10" }

$Venv = Join-Path $Prefix "venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"
$Paws = Join-Path $Venv "Scripts\paws.exe"
$version = & $Python @PyArgs -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"

Say "paws: installing from $Src"
Say "  python   $Python $($PyArgs -join ' ') ($version)"
Say "  into     $Venv"
Say "  command  $Paws"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Say "  note: git isn't installed, so ``paws update`` won't work until it is (winget install Git.Git)" }

$Type = if ($Riced) { "riced" } elseif ($Minimal) { "minimal" } else { $env:PAWS_TYPE }
if (-not $Type -and -not $DryRun) {
    $answer = Read-Host "  look: [r]iced (picture, banner, ascii art) or [m]inimal (plain text)? [r]"
    $Type = if ($answer -match '^[mM]') { "minimal" } else { "riced" }
}
if (-not $Type) { $Type = "riced" }

# ---- the private environment ----------------------------------------------------------------------
if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $Prefix | Out-Null }
Run $Python ($PyArgs + @("-m", "venv", $Venv))
$Spec = if ($Type -eq "riced") { "$Src[riced]" } else { $Src }
Run $VenvPy @("-m", "pip", "install", "--quiet", "--disable-pip-version-check", $Spec)
if ($Type -eq "minimal") { Push-Location $env:SystemDrive\; Run $VenvPy @("-m", "paws.riced", "prune"); Pop-Location }

# ---- start menu + PATH (nothing here opens a window) ------------------------------------------------
if (-not $NoDesktop) { Run $Paws @("desktop") }
if (-not $NoAlias) { Run $Paws @("alias", "--install") }

if ($DryRun) {
    Say "  would set the look to $Type"
} else {
    $Config = if ($env:PAWS_CONFIG_DIR) { $env:PAWS_CONFIG_DIR } else { Join-Path $env:APPDATA "paws" }
    if (-not (Test-Path (Join-Path $Config "settings.json"))) {
        New-Item -ItemType Directory -Force -Path $Config | Out-Null
        # utf-8 without a BOM, python's json reader chokes on the one Set-Content -Encoding utf8 adds on 5.1
        [System.IO.File]::WriteAllText((Join-Path $Config "settings.json"), "{`n  `"type`": `"$Type`"`n}`n")
    } else {
        & $Paws settings type $Type | Out-Null
    }
    Say "  look     $Type (change it any time in Settings > Type)"
}

if ($DryRun) { Say "dry run: nothing was changed" } else { Say "done. open a new terminal and run: paws  (or find paws in the start menu)" }
