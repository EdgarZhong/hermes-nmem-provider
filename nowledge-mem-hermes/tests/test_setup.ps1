$ErrorActionPreference = "Stop"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Setup = Join-Path $Root "setup.ps1"
$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("personal-hermes-test-" + [guid]::NewGuid())
$OldHome = $env:HERMES_HOME
New-Item -ItemType Directory -Path $TempRoot | Out-Null
try {
    $env:HERMES_HOME = Join-Path $TempRoot "profile with spaces"
    New-Item -ItemType Directory -Path $env:HERMES_HOME | Out-Null
    [IO.File]::WriteAllText((Join-Path $env:HERMES_HOME "config.yaml"), "model: keep-this-model`nmemory:`n  nudge_interval: 17`n")
    [IO.File]::WriteAllText((Join-Path $env:HERMES_HOME "USER.md"), "preserve user-owned memory")
    $Preview = & python (Join-Path $Root "install_personal.py") --home $env:HERMES_HOME
    if ($LASTEXITCODE -ne 0) { throw "Preview failed" }
    if (($Preview | ConvertFrom-Json).status -ne "preview") { throw "Invalid preview" }
    if (Test-Path (Join-Path $env:HERMES_HOME "plugins")) { throw "Preview wrote plugin files" }
    $Output = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Setup
    if ($LASTEXITCODE -ne 0) { throw "Installer failed" }
    $Result = $Output | ConvertFrom-Json
    if ($Result.status -ne "installed") { throw "No installation receipt" }
    if (-not (Test-Path (Join-Path $Result.backup "config.yaml"))) { throw "Configuration backup missing" }
    & python -c "import os,pathlib,yaml; p=pathlib.Path(os.environ['HERMES_HOME']); c=yaml.safe_load((p/'config.yaml').read_text()); assert c['model']=='keep-this-model'; assert c['memory']=={'nudge_interval':17,'provider':'nowledge-mem','memory_enabled':False,'user_profile_enabled':False}; assert (p/'USER.md').read_text()=='preserve user-owned memory'; assert (p/'plugins/nowledge-mem/personal_provider.py').is_file(); assert (p/'plugins/nowledge-mem/skills/nm-cli/SKILL.md').is_file()"
    if ($LASTEXITCODE -ne 0) { throw "Installed content verification failed" }
    $Before = [IO.File]::ReadAllText((Join-Path $env:HERMES_HOME "config.yaml"))
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Setup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Reinstall failed" }
    if ([IO.File]::ReadAllText((Join-Path $env:HERMES_HOME "config.yaml")) -ne $Before) { throw "Reinstall changed configuration" }

    $env:HERMES_HOME = Join-Path $TempRoot "conflicting-provider"
    New-Item -ItemType Directory -Path $env:HERMES_HOME | Out-Null
    $Conflict = "memory:`n  provider: different-provider`n"
    [IO.File]::WriteAllText((Join-Path $env:HERMES_HOME "config.yaml"), $Conflict)
    $OldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Setup 2>&1 | Out-Null
    $Code = $LASTEXITCODE
    $ErrorActionPreference = $OldPreference
    if ($Code -eq 0) { throw "Conflicting provider was not rejected" }
    if ([IO.File]::ReadAllText((Join-Path $env:HERMES_HOME "config.yaml")) -ne $Conflict) { throw "Conflict changed configuration" }
    if (Test-Path (Join-Path $env:HERMES_HOME "plugins")) { throw "Conflict installed plugin files" }
    Write-Output "Personal PowerShell installer: preview, install, backup, repeat and conflict checks passed."
} finally {
    $env:HERMES_HOME = $OldHome
    Remove-Item -Recurse -Force $TempRoot
}
