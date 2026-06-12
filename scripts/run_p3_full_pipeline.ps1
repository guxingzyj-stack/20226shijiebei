# P3 full local pipeline helper.
#
# Purpose:
# - Run P3-Light recent performance dry-run checks.
# - Run the FIFA Match Centre pipeline helper.
# - Optionally run full pytest.
# - Run simple local safety checks.
#
# Safety boundaries:
# - Does not write production DB.
# - Does not run migrations.
# - Does not deploy Zeabur services.
# - Does not enable betting.
# - Does not modify crawler/.
# - Does not fabricate player data.
# - Does not commit probe_*.json, backups, .env, raw cache, or secrets.

param(
    [object]$RunPytest = $true,
    [switch]$AllowCommit
)

$ErrorActionPreference = "Stop"

function ConvertTo-Bool {
    param([object]$Value)

    if ($Value -is [bool]) {
        return $Value
    }

    $text = "$Value".Trim().ToLowerInvariant()
    if ($text -in @("false", "0", "no", "n", "off")) {
        return $false
    }
    if ($text -in @("true", "1", "yes", "y", "on", "")) {
        return $true
    }

    throw "Cannot convert RunPytest value to bool: $Value"
}

function Step {
    param([string]$Message)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host $Message -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function RunCmd {
    param([string]$Command)

    Write-Host ""
    Write-Host "> $Command" -ForegroundColor Yellow
    cmd.exe /d /c $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Command"
    }
}

$shouldRunPytest = ConvertTo-Bool $RunPytest
$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Step "0. Enter project root"

Set-Location $RootDir
$env:PYTHONPATH = "."

Write-Host "Project root: $RootDir"
Write-Host "PYTHONPATH: $env:PYTHONPATH"

Step "1. Safety environment check"

if ($env:BETTING_ENABLED -eq "true") {
    throw "BETTING_ENABLED=true detected. Stop."
}

if ($env:DATABASE_URL) {
    Write-Host "WARNING: DATABASE_URL is set. This helper only runs dry-run/local tools." -ForegroundColor Yellow
}

Write-Host "BETTING_ENABLED: $env:BETTING_ENABLED"
Write-Host "DATABASE_URL set: $([bool]$env:DATABASE_URL)"

Step "2. Git status before run"
RunCmd "git status --short"

Step "3. P3-Light recent performance dry-run"

$lightCsvFile = Join-Path $RootDir "data\p3\real_performance_squad.csv"
if (!(Test-Path $lightCsvFile)) {
    Write-Host "real_performance_squad.csv not found." -ForegroundColor Yellow
    Write-Host "P3-Light continues with existing real_performance_*.csv files, if any." -ForegroundColor Yellow
}

RunCmd "python -m model.p3_ingest validate-real --dry-run"
RunCmd "python -m model.p3_ingest build-team-features-real --dry-run"
RunCmd "python -m model.p3d_acceptance_report --dry-run"
RunCmd "python -m ops.next_phase_acceptance"

Step "4. FIFA Match Centre pipeline"
RunCmd "powershell -ExecutionPolicy Bypass -File `".\scripts\run_p3_fifa_match_pipeline.ps1`" -RunPytest false"

if ($shouldRunPytest) {
    Step "5. Full pytest"
    RunCmd "python -m pytest tests/ -q"
} else {
    Write-Host "Skip pytest because RunPytest is false." -ForegroundColor Yellow
}

Step "6. Safety grep"

RunCmd "git grep -n `"postgresql://`" || exit /b 0"
RunCmd "git grep -n `"DATABASE_URL`" || exit /b 0"
RunCmd "git grep -n `"THE_ODDS_API_KEY`" || exit /b 0"
RunCmd "git grep -n `"FBref`" || exit /b 0"
RunCmd "git grep -n `"Transfermarkt`" || exit /b 0"

Step "7. Forbidden local file check"

$forbiddenPatterns = @("probe_*.json", ".env")
$forbiddenDirs = @("backups", "data\p3\statsbomb_open_data")

foreach ($pattern in $forbiddenPatterns) {
    $matches = Get-ChildItem -Path $RootDir -Filter $pattern -Recurse -Force -ErrorAction SilentlyContinue
    foreach ($match in $matches) {
        Write-Host "WARNING: forbidden local file pattern found, do not commit: $($match.FullName)" -ForegroundColor Yellow
    }
}

foreach ($dir in $forbiddenDirs) {
    $fullDir = Join-Path $RootDir $dir
    if (Test-Path $fullDir) {
        Write-Host "WARNING: forbidden/local-only directory found, do not commit: $fullDir" -ForegroundColor Yellow
    }
}

RunCmd "git status --short"

Step "8. Optional commit"

if ($AllowCommit) {
    Write-Host "AllowCommit enabled. Only this wrapper script will be staged." -ForegroundColor Yellow
    RunCmd "git add `"scripts/run_p3_full_pipeline.ps1`""
    RunCmd "git diff --cached --name-only"
    RunCmd "git commit -m `"p3: add full local pipeline runner`""
    RunCmd "git push origin main"
} else {
    Write-Host "AllowCommit disabled. No git commit performed." -ForegroundColor Yellow
}

Step "9. Final summary"

Write-Host "P3 full local pipeline completed." -ForegroundColor Green
Write-Host "Expected state: P3 may remain WAIT until legal performance coverage reaches 70% per team." -ForegroundColor Cyan
Write-Host "Production GBM remains disabled unless a separate reviewed deployment changes production weights." -ForegroundColor Cyan
