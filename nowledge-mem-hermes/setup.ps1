$ErrorActionPreference = "Stop"
$homeDir = $env:HERMES_HOME
if (-not $homeDir) { $homeDir = Join-Path $env:LOCALAPPDATA "hermes" }
python (Join-Path $PSScriptRoot "install_personal.py") --home $homeDir --apply @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
