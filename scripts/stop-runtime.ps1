param(
    [switch]$RemoveOrphans
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$srcRoot = Join-Path $repoRoot "src"
$previousPythonPath = $env:PYTHONPATH

$commandArgs = @(
    "-m",
    "trotters_trader.cli",
    "research-stack-down"
)

if ($RemoveOrphans) {
    $commandArgs += "--remove-orphans"
}

if ([string]::IsNullOrWhiteSpace($previousPythonPath)) {
    $env:PYTHONPATH = $srcRoot
} else {
    $env:PYTHONPATH = "$srcRoot;$previousPythonPath"
}

Push-Location $repoRoot
try {
    & python @commandArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}
