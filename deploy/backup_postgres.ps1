$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$EnvFile = Join-Path $RootDir ".env"
$BackupDir = Join-Path $RootDir "backups"

if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      return
    }
    $parts = $line.Split("=", 2)
    $name = $parts[0].Trim()
    $value = $parts[1].Trim().Trim('"').Trim("'")
    if (-not [Environment]::GetEnvironmentVariable($name)) {
      [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
  }
}

$DbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "worldcup" }
$DbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "worldcup_app" }
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$OutFile = Join-Path $BackupDir "worldcup_$Timestamp.sql"

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

Write-Host "Backing up PostgreSQL database '$DbName' to $OutFile"
docker compose -f (Join-Path $RootDir "docker-compose.yml") exec -T postgres pg_dump -U $DbUser -d $DbName --no-owner --no-privileges | Out-File -FilePath $OutFile -Encoding utf8
Write-Host "Backup complete: $OutFile"
