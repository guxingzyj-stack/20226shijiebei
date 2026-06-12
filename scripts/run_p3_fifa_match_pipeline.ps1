# P3-Light FIFA Match Centre pipeline helper.
#
# Purpose:
# - Check whether data/p3/fifa_match_targets.csv exists.
# - Probe FIFA Match Centre URLs.
# - Build data/p3/real_performance_fifa_match_sample.csv when official
#   player-level FIFA data is available.
# - Run P3 dry-run validation, acceptance checks, optional pytest, and safety
#   grep in one command.
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
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TargetsCsv = "data\p3\fifa_match_targets.csv",
    [string]$ReportOut = "docs\P3_FIFA_MATCH_DATA_REPORT.md",
    [string]$SampleOut = "data\p3\real_performance_fifa_match_sample.csv",
    [string]$UnmatchedOut = "data\p3\real_performance_unmatched_fifa.csv",
    [object]$RunPytest = $true,
    [switch]$AllowCommit
)

$ErrorActionPreference = "Stop"

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

function Write-EmbeddedPython {
    param(
        [string]$Name,
        [string]$Code
    )

    $path = Join-Path $env:TEMP $Name
    Set-Content -Path $path -Value $Code -Encoding UTF8
    return $path
}

$shouldRunPytest = ConvertTo-Bool $RunPytest

Step "0. Enter project root"

if (!(Test-Path $ProjectRoot)) {
    throw "ProjectRoot not found: $ProjectRoot"
}

Set-Location $ProjectRoot
$env:PYTHONPATH = "."

Write-Host "ProjectRoot: $ProjectRoot"
Write-Host "PYTHONPATH: $env:PYTHONPATH"

Step "1. Git status before run"
RunCmd "git status --short"

Step "2. Safety environment check"

if ($env:BETTING_ENABLED -eq "true") {
    throw "BETTING_ENABLED=true detected. Stop."
}

if ($env:DATABASE_URL) {
    Write-Host "WARNING: DATABASE_URL is set. This script only runs dry-run/local tools." -ForegroundColor Yellow
}

Write-Host "BETTING_ENABLED: $env:BETTING_ENABLED"
Write-Host "DATABASE_URL set: $([bool]$env:DATABASE_URL)"

Step "3. Check FIFA match targets CSV"

$fullTargetsPath = Join-Path $ProjectRoot $TargetsCsv
$targetsReady = $false

if (!(Test-Path $fullTargetsPath)) {
    Write-Host "Missing FIFA match targets: $TargetsCsv" -ForegroundColor Yellow
    Write-Host "Result: WAIT / blocker=missing_fifa_match_url_mapping" -ForegroundColor Yellow
    Write-Host "Expected columns: project_match_id,fifa_match_url,home_team,away_team,kickoff_at,status" -ForegroundColor Yellow

    Step "3.1 Generate/confirm template and report"
    RunCmd "python -m tools.p3_probe_fifa_match_centre --matches `"$TargetsCsv`" --report-out `"$ReportOut`""
    RunCmd "python -m tools.p3_build_fifa_match_performance_csv --matches `"$TargetsCsv`" --squad data/p3/manual_real_squad.csv --out `"$SampleOut`" --unmatched-out `"$UnmatchedOut`" --report-out `"$ReportOut`""
} else {
    Write-Host "FIFA match targets found: $TargetsCsv" -ForegroundColor Green

    Step "3.1 Static target CSV check"

    $targetCheck = @'
from pathlib import Path
import csv
import sys

path = Path(r"data/p3/fifa_match_targets.csv")
required_header = ["project_match_id","fifa_match_url","home_team","away_team","kickoff_at","status"]

if not path.exists():
    print("TARGETS_MISSING")
    sys.exit(0)

with path.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames or []
    rows = list(reader)

missing = [h for h in required_header if h not in headers]
empty_url = [i + 2 for i, r in enumerate(rows) if not (r.get("fifa_match_url") or "").strip()]
non_fifa = [
    i + 2 for i, r in enumerate(rows)
    if (r.get("fifa_match_url") or "").strip()
    and "fifa.com" not in (r.get("fifa_match_url") or "").lower()
    and not Path((r.get("fifa_match_url") or "").strip()).exists()
]

print(f"headers={headers}")
print(f"rows={len(rows)}")
print(f"missing_headers={missing}")
print(f"empty_url_rows={empty_url[:20]}")
print(f"non_fifa_url_rows={non_fifa[:20]}")

if missing:
    print("TARGET_STATIC_CHECK=FAIL")
    sys.exit(2)

if non_fifa:
    print("TARGET_STATIC_CHECK=FAIL_NON_FIFA_URL")
    sys.exit(3)

if empty_url:
    print("TARGET_STATIC_CHECK=WAIT_MISSING_URL")
else:
    print("TARGET_STATIC_CHECK=PASS")
'@

    $tmpTargetCheck = Write-EmbeddedPython "p3_fifa_targets_check.py" $targetCheck
    RunCmd "python `"$tmpTargetCheck`""

    $targetsReady = $true
}

if ($targetsReady) {
    Step "4. Probe FIFA Match Centre URLs"
    RunCmd "python -m tools.p3_probe_fifa_match_centre --matches `"$TargetsCsv`" --report-out `"$ReportOut`""

    Step "5. Build FIFA MatchData sample CSV"
    RunCmd "python -m tools.p3_build_fifa_match_performance_csv --matches `"$TargetsCsv`" --squad data/p3/manual_real_squad.csv --out `"$SampleOut`" --unmatched-out `"$UnmatchedOut`" --report-out `"$ReportOut`""

    Step "5.1 Static sample CSV check"

    $sampleCheck = @'
from pathlib import Path
import csv
import sys

path = Path(r"data/p3/real_performance_fifa_match_sample.csv")
required_header = [
    "team","player_name","club","minutes_recent","goals_recent","assists_recent",
    "xg_recent","xa_recent","source","retrieved_at","confidence","notes"
]

if not path.exists():
    print("SAMPLE_CSV_MISSING")
    sys.exit(0)

with path.open("r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    headers = reader.fieldnames or []
    rows = list(reader)

missing = [h for h in required_header if h not in headers]
example_rows = [i + 2 for i, r in enumerate(rows) if "EXAMPLE_ONLY_DO_NOT_USE" in str(r)]
bad_conf = [i + 2 for i, r in enumerate(rows) if r.get("confidence") not in ("high", "medium", "low")]
missing_source = [i + 2 for i, r in enumerate(rows) if not (r.get("source") or "").strip()]
missing_retrieved_at = [i + 2 for i, r in enumerate(rows) if not (r.get("retrieved_at") or "").strip()]
missing_notes = [i + 2 for i, r in enumerate(rows) if not (r.get("notes") or "").strip()]
missing_unavailable_xgxa = [
    i + 2 for i, r in enumerate(rows)
    if ((not (r.get("xg_recent") or "").strip()) or (not (r.get("xa_recent") or "").strip()))
    and "unavailable" not in (r.get("notes") or "").lower()
]

print(f"headers={headers}")
print(f"rows={len(rows)}")
print(f"missing_headers={missing}")
print(f"example_rows={example_rows[:20]}")
print(f"bad_confidence_rows={bad_conf[:20]}")
print(f"missing_source_rows={missing_source[:20]}")
print(f"missing_retrieved_at_rows={missing_retrieved_at[:20]}")
print(f"missing_notes_rows={missing_notes[:20]}")
print(f"missing_unavailable_xgxa_rows={missing_unavailable_xgxa[:20]}")

if missing or example_rows or bad_conf or missing_source or missing_retrieved_at or missing_notes or missing_unavailable_xgxa:
    print("SAMPLE_STATIC_CHECK=FAIL")
    sys.exit(2)

print("SAMPLE_STATIC_CHECK=PASS")
'@

    $tmpSampleCheck = Write-EmbeddedPython "p3_fifa_sample_check.py" $sampleCheck
    RunCmd "python `"$tmpSampleCheck`""
} else {
    Write-Host "Skipping FIFA build because URL mapping is missing." -ForegroundColor Yellow
}

Step "6. P3-Light dry-run validation"
RunCmd "python -m model.p3_ingest validate-real --dry-run"

Step "7. Build team features dry-run"
RunCmd "python -m model.p3_ingest build-team-features-real --dry-run"

Step "8. P3D acceptance dry-run"
RunCmd "python -m model.p3d_acceptance_report --dry-run"

Step "9. Next phase acceptance"
RunCmd "python -m ops.next_phase_acceptance"

if ($shouldRunPytest) {
    Step "10. Full pytest"
    RunCmd "python -m pytest tests/ -q"
} else {
    Write-Host "Skip pytest because RunPytest is false." -ForegroundColor Yellow
}

Step "11. Safety grep"

Write-Host "Checking sensitive patterns. Documentation/test placeholders may be acceptable; real keys are not." -ForegroundColor Yellow

RunCmd "git grep -n `"postgresql://`" || exit /b 0"
RunCmd "git grep -n `"DATABASE_URL`" || exit /b 0"
RunCmd "git grep -n `"THE_ODDS_API_KEY`" || exit /b 0"
RunCmd "git grep -n `"FBref`" || exit /b 0"
RunCmd "git grep -n `"Transfermarkt`" || exit /b 0"

Step "12. Check forbidden local files"

RunCmd "git status --short"

$status = git status --short
$forbidden = @(
    "probe_",
    "backups/",
    ".env",
    "data/p3/statsbomb_open_data/",
    "raw_cache",
    "html_cache"
)

foreach ($line in $status) {
    foreach ($bad in $forbidden) {
        if ($line -like "*$bad*") {
            Write-Host "WARNING forbidden local file pattern detected, do not commit: $line" -ForegroundColor Yellow
        }
    }
}

Step "13. Optional commit"

if ($AllowCommit) {
    Write-Host "AllowCommit enabled." -ForegroundColor Yellow

    $filesToAdd = @(
        "tools/p3_probe_fifa_match_centre.py",
        "tools/p3_build_fifa_match_performance_csv.py",
        "tests/tools_tests/test_p3_probe_fifa_match_centre.py",
        "tests/tools_tests/test_p3_build_fifa_match_performance_csv.py",
        "docs/P3_FIFA_MATCH_DATA_REPORT.md",
        "docs/P3_RECENT_PERFORMANCE_DATA_GUIDE.md",
        "docs/P3_MANUAL_DATA_GUIDE.md",
        "docs/P3D_REAL_DATA_SOURCE_PLAN.md",
        "data/p3/fifa_match_targets_template.csv",
        "scripts/run_p3_fifa_match_pipeline.ps1"
    )

    if (Test-Path "data/p3/real_performance_fifa_match_sample.csv") {
        $filesToAdd += "data/p3/real_performance_fifa_match_sample.csv"
    }

    if (Test-Path "data/p3/real_performance_unmatched_fifa.csv") {
        $filesToAdd += "data/p3/real_performance_unmatched_fifa.csv"
    }

    $addLine = "git add " + (($filesToAdd | ForEach-Object { "`"$_`"" }) -join " ")
    RunCmd $addLine

    RunCmd "git diff --cached --name-only"
    Write-Host "Review staged files above. Forbidden files must not appear." -ForegroundColor Yellow

    RunCmd "git commit -m `"p3: add fifa match centre pipeline runner`""
    RunCmd "git push origin main"
} else {
    Write-Host "AllowCommit disabled. No git commit performed." -ForegroundColor Yellow
}

Step "14. Final summary"

Write-Host "P3 FIFA Match Centre pipeline completed." -ForegroundColor Green
Write-Host ""
Write-Host "Expected outcomes:" -ForegroundColor Cyan
Write-Host "1. If fifa_match_targets.csv is missing: result=WAIT, blocker=missing_fifa_match_url_mapping." -ForegroundColor Cyan
Write-Host "2. If URLs exist but no player data: result=WAIT, no fake CSV." -ForegroundColor Cyan
Write-Host "3. If official player data exists: sample CSV generated from FIFA official source." -ForegroundColor Cyan
Write-Host "4. If coverage <70%: gbm_ready=false, candidate_w_gbm=0." -ForegroundColor Cyan
Write-Host "5. If coverage >=70%: gbm_ready=true, candidate_w_gbm=0.2, production_w_gbm=0." -ForegroundColor Cyan
Write-Host "6. Betting remains disabled. Production GBM is not auto-enabled." -ForegroundColor Cyan
