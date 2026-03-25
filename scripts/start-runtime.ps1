param(
    [int]$WorkerCount = 5,
    [switch]$NoBuild,
    [switch]$Foreground,
    [switch]$RemoveOrphans,
    [switch]$UsePostgres,
    [string]$RuntimeDatabaseUrl
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$srcRoot = Join-Path $repoRoot "src"
$previousPythonPath = $env:PYTHONPATH
$previousComposeProfiles = $env:COMPOSE_PROFILES
$previousRuntimeDatabaseUrl = $env:TROTTERS_RUNTIME_DATABASE_URL

$commandArgs = @(
    "-m",
    "trotters_trader.cli",
    "research-stack-up",
    "--worker-count",
    $WorkerCount
)

if ($NoBuild) {
    $commandArgs += "--no-build"
}
if ($Foreground) {
    $commandArgs += "--foreground"
}
if ($RemoveOrphans) {
    $commandArgs += "--remove-orphans"
}

if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $srcRoot
} else {
    $env:PYTHONPATH = "$srcRoot;$previousPythonPath"
}

if ($UsePostgres -or -not [string]::IsNullOrWhiteSpace($RuntimeDatabaseUrl)) {
    if ([string]::IsNullOrWhiteSpace($RuntimeDatabaseUrl)) {
        $runtimeDbPassword = if ([string]::IsNullOrWhiteSpace($env:TROTTERS_RUNTIME_DB_PASSWORD)) {
            "trotters-runtime-local"
        } else {
            $env:TROTTERS_RUNTIME_DB_PASSWORD
        }
        $resolvedRuntimeDatabaseUrl = "postgresql://trotters:$runtimeDbPassword@runtime-db:5432/trotters_runtime"
    } else {
        $resolvedRuntimeDatabaseUrl = $RuntimeDatabaseUrl
    }
    $env:TROTTERS_RUNTIME_DATABASE_URL = $resolvedRuntimeDatabaseUrl
    if ([string]::IsNullOrWhiteSpace($previousComposeProfiles)) {
        $env:COMPOSE_PROFILES = "postgres"
    } elseif (($previousComposeProfiles -split ',') -notcontains 'postgres') {
        $env:COMPOSE_PROFILES = "$previousComposeProfiles,postgres"
    }
}

Push-Location $repoRoot
try {
    & python @commandArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
    $env:COMPOSE_PROFILES = $previousComposeProfiles
    $env:TROTTERS_RUNTIME_DATABASE_URL = $previousRuntimeDatabaseUrl
}
