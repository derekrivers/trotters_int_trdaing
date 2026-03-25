param(
    [string]$BackupRoot = "runtime/backups",
    [string]$ComposeProjectName,
    [string]$VolumeName
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path

if ([string]::IsNullOrWhiteSpace($ComposeProjectName)) {
    $ComposeProjectName = [IO.Path]::GetFileName($repoRoot).ToLowerInvariant()
}
if ([string]::IsNullOrWhiteSpace($VolumeName)) {
    $VolumeName = "${ComposeProjectName}_research_runtime"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupRootPath = if ([IO.Path]::IsPathRooted($BackupRoot)) {
    $BackupRoot
} else {
    Join-Path $repoRoot $BackupRoot
}
$snapshotDir = Join-Path $backupRootPath "runtime_snapshot_$timestamp"
$catalogSource = Join-Path $repoRoot "runtime/catalog"
$openClawSource = Join-Path $repoRoot "runtime/openclaw"
$catalogBackup = Join-Path $snapshotDir "catalog"
$openClawBackup = Join-Path $snapshotDir "openclaw"
$sqliteBackupPath = Join-Path $snapshotDir "research_runtime.sqlite3"
$volumeTarPath = Join-Path $snapshotDir "research_runtime_volume.tar"
$manifestPath = Join-Path $snapshotDir "manifest.json"
$readmePath = Join-Path $snapshotDir "README.txt"

New-Item -ItemType Directory -Force -Path $snapshotDir | Out-Null

if (Test-Path $catalogSource) {
    Copy-Item -Path $catalogSource -Destination $catalogBackup -Recurse -Force
}
if (Test-Path $openClawSource) {
    Copy-Item -Path $openClawSource -Destination $openClawBackup -Recurse -Force
}

$dockerPythonScript = @"
import sqlite3
import tarfile
from pathlib import Path

source_root = Path('/source')
backup_root = Path('/backup')
db_path = source_root / 'state' / 'research_runtime.sqlite3'
sqlite_backup = backup_root / 'research_runtime.sqlite3'
tar_path = backup_root / 'research_runtime_volume.tar'

if db_path.exists():
    source = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    destination = sqlite3.connect(sqlite_backup)
    source.backup(destination)
    destination.close()
    source.close()

with tarfile.open(tar_path, 'w') as archive:
    for path in source_root.rglob('*'):
        archive.add(path, arcname=path.relative_to(source_root))
"@

$dockerArgs = @(
    'run',
    '--rm',
    '-v', "${VolumeName}:/source:ro",
    '-v', "${snapshotDir}:/backup",
    'python:3.11-slim',
    'python',
    '-c',
    $dockerPythonScript
)

& docker @dockerArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to export Docker volume '$VolumeName'."
}

$gitCommit = ''
try {
    $gitCommit = (git -C $repoRoot rev-parse HEAD).Trim()
} catch {
    $gitCommit = ''
}

$catalogExists = Test-Path $catalogBackup
$openClawExists = Test-Path $openClawBackup
$manifest = [ordered]@{
    created_at_utc = [DateTimeOffset]::UtcNow.ToString('o')
    snapshot_dir = $snapshotDir
    compose_project_name = $ComposeProjectName
    runtime_volume = $VolumeName
    git_commit = $gitCommit
    includes = [ordered]@{
        catalog = $catalogExists
        openclaw = $openClawExists
        sqlite_backup = (Test-Path $sqliteBackupPath)
        research_runtime_volume_tar = (Test-Path $volumeTarPath)
    }
    restore_notes = @(
        'runtime/catalog and runtime/openclaw were copied as host-side snapshots.',
        'research_runtime.sqlite3 is a consistent SQLite backup made from the live Docker volume.',
        'research_runtime_volume.tar is a full file-level export of the Docker volume for job outputs, logs, exports, and state recovery.'
    )
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Path $manifestPath -Encoding utf8

$readme = @"
Runtime backup created at $timestamp UTC.

Contents:
- catalog/: host-side snapshot of runtime/catalog
- openclaw/: host-side snapshot of runtime/openclaw
- research_runtime.sqlite3: consistent SQLite backup from the live Docker volume
- research_runtime_volume.tar: full export of the Docker research_runtime volume
- manifest.json: backup metadata

Intended use:
- recover catalog and OpenClaw state from the copied folders
- recover runtime DB quickly from research_runtime.sqlite3
- recover full named-volume contents from research_runtime_volume.tar if job outputs, logs, or exports are needed
"@
$readme | Set-Content -Path $readmePath -Encoding utf8

$result = [ordered]@{
    snapshot_dir = $snapshotDir
    compose_project_name = $ComposeProjectName
    runtime_volume = $VolumeName
    catalog_snapshot = $catalogExists
    openclaw_snapshot = $openClawExists
    sqlite_backup = (Test-Path $sqliteBackupPath)
    research_runtime_volume_tar = (Test-Path $volumeTarPath)
}
$result | ConvertTo-Json -Depth 4
