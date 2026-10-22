# ListingAssistants - Windows installer (one line, no admin rights)
#
#   iex (irm https://raw.githubusercontent.com/QuietFireAI/listing-assistants/main/install.ps1)
#
# What it does, all under one folder of your own (default
# %LOCALAPPDATA%\ListingAssistants); deleting that folder and the two desktop
# shortcuts removes everything:
#   1. fetches uv (a Python manager), pinned below, into tools\
#   2. fetches a private Python 3.12 into python\ (your other Pythons are not
#      touched; nothing is added to PATH)
#   3. downloads ListingAssistants into app\ and installs its requirements
#      into venv\
#   4. first install: makes your operator key and records who you are, in
#      state\ (your records live there and are kept on every reinstall);
#      then attests the install you just put in place
#   5. desktop shortcuts: "ListingAssistants Desk" and "ListingAssistants
#      Playbook Show"
#   6. Hermes: adds ListingAssistants to Hermes' MCP servers when Hermes is
#      installed (keeps a copy of its old settings); always saves the block
#      in hermes-mcp.yaml
#
# Settings (environment variables, all optional):
#   LA_HOME          install folder        (default %LOCALAPPDATA%\ListingAssistants)
#   LA_REF           branch, tag or commit (default main)
#   LA_NAME,LA_LOGIN your name and email   (asked for if not set, first install only)
#   LA_NO_SHORTCUTS  set to 1 for no desktop shortcuts
#   LA_NO_HERMES     set to 1 to leave Hermes' settings alone
#   HERMES_HOME      where Hermes keeps config.yaml (default %LOCALAPPDATA%\hermes,
#                    then %USERPROFILE%\.hermes)
#
# Owner decision 2026-10-21: one PowerShell line first; a signed setup
# wizard (.exe) comes later, with a code-signing certificate.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is many times slower with the bar on

$UvVersion = "0.12.23"
$PythonVersion = "3.12"
$Repo = "QuietFireAI/listing-assistants"

function Say($text) { Write-Host "  $text" }
function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host ""; Write-Host "INSTALL STOPPED: $text" -ForegroundColor Red; throw $text }

$LaHome = if ($env:LA_HOME) { $env:LA_HOME } else { Join-Path $env:LOCALAPPDATA "ListingAssistants" }
# a full path with no ".." in it, so paths compare as Python reports them
$LaHome = [System.IO.Path]::GetFullPath($LaHome)
$Ref = if ($env:LA_REF) { $env:LA_REF } else { "main" }
$Tools = Join-Path $LaHome "tools"
$PyDir = Join-Path $LaHome "python"
$App = Join-Path $LaHome "app"
$Venv = Join-Path $LaHome "venv"
$State = Join-Path $LaHome "state"
$Py = Join-Path $Venv "Scripts\python.exe"

Write-Host "ListingAssistants installer" -ForegroundColor Cyan
Say "folder:  $LaHome"
Say "version: $Ref"
New-Item -ItemType Directory -Force -Path $LaHome, $Tools | Out-Null

# --- 1. uv ------------------------------------------------------------------
Step "1/6 Python manager (uv $UvVersion)"
$arch = if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") { "aarch64" } else { "x86_64" }
$Uv = Join-Path $Tools "uv.exe"
$haveUv = (Test-Path $Uv) -and ((& $Uv --version) -match [regex]::Escape($UvVersion))
if (-not $haveUv) {
    $zip = Join-Path $Tools "uv.zip"
    $url = "https://github.com/astral-sh/uv/releases/download/$UvVersion/uv-$arch-pc-windows-msvc.zip"
    Say "downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $Tools -Force
    Remove-Item $zip
}
if (-not (Test-Path $Uv)) { Fail "uv.exe is not in $Tools after the download" }
Say (& $Uv --version)

# uv keeps its Pythons and its cache inside this folder, not in your profile
$env:UV_PYTHON_INSTALL_DIR = $PyDir
$env:UV_CACHE_DIR = Join-Path $LaHome "cache"
$env:UV_PYTHON_PREFERENCE = "only-managed"

# --- 2. Python ----------------------------------------------------------------
Step "2/6 private Python $PythonVersion"
& $Uv python install $PythonVersion
if ($LASTEXITCODE -ne 0) { Fail "uv could not install Python $PythonVersion" }

# --- 3. the app -----------------------------------------------------------------
Step "3/6 ListingAssistants ($Ref)"
$src = if ($env:LA_SOURCE_ZIP) { $env:LA_SOURCE_ZIP } else { "https://github.com/$Repo/archive/$Ref.zip" }
$zip = Join-Path $LaHome "app.zip"
$unpack = Join-Path $LaHome "app.new"
if (Test-Path $unpack) { Remove-Item -Recurse -Force $unpack }
if (Test-Path $src) { Copy-Item $src $zip } else {
    Say "downloading $src"
    Invoke-WebRequest -Uri $src -OutFile $zip -UseBasicParsing
}
Expand-Archive -Path $zip -DestinationPath $unpack -Force
Remove-Item $zip
$top = Get-ChildItem $unpack -Directory | Select-Object -First 1
if (-not $top -or -not (Test-Path (Join-Path $top.FullName "tools\desk.py"))) { Fail "the download does not hold tools\desk.py" }
if (Test-Path $App) { Remove-Item -Recurse -Force $App }
Move-Item $top.FullName $App
Remove-Item -Recurse -Force $unpack

# a new environment each time, so nothing from an earlier version is left in it
if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }
& $Uv venv $Venv --python $PythonVersion
if ($LASTEXITCODE -ne 0) { Fail "uv could not make the environment in $Venv" }
& $Uv pip install --python $Py -r (Join-Path $App "requirements.txt")
if ($LASTEXITCODE -ne 0) { Fail "the requirements did not install" }
$base = & $Py -c "import sys; print(sys.base_prefix)"
if (-not $base.StartsWith($PyDir, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail "the environment is not on the private Python (it uses $base, expected under $PyDir)"
}
Say "Python: $base"

# --- 4. your key, who you are, the attestation ----------------------------------------
Step "4/6 your key and the install check"
$env:LISTINGASSISTANTS_STATE_DIR = $State
$console = Join-Path $App "tools\console.py"
if (-not (Test-Path (Join-Path $State "operator-key.bin"))) {
    & $Py $console init
    if ($LASTEXITCODE -ne 0) { Fail "console init did not finish" }
    $name = $(if ($env:LA_NAME) { $env:LA_NAME } else { Read-Host "Your name (broker of record)" }).Trim()
    $login = $(if ($env:LA_LOGIN) { $env:LA_LOGIN } else { Read-Host "Your login (the email you sign as)" }).Trim()
    & $Py $console onboard --name $name --login $login
    if ($LASTEXITCODE -ne 0) { Fail "onboarding did not finish" }
} else {
    Say "your key and records in $State are kept"
    # the operator who runs the installer attests the code it just put in place
    & $Py $console attest
    if ($LASTEXITCODE -ne 0) { Fail "the install check (attest) did not finish" }
}

# --- 5. launchers and shortcuts ---------------------------------------------------
Step "5/6 launchers"
$deskCmd = Join-Path $LaHome "Desk.cmd"
$showCmd = Join-Path $LaHome "Playbook Show.cmd"
@"
@echo off
rem ListingAssistants Broker Desk - your own records (state\)
set LISTINGASSISTANTS_STATE_DIR=%~dp0state
start "" powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/ | Out-Null; break } catch { Start-Sleep -Seconds 1 } }; Start-Process http://127.0.0.1:8765/"
"%~dp0venv\Scripts\python.exe" "%~dp0app\tools\desk.py"
if errorlevel 1 (echo. & echo The desk stopped with the error above. & pause)
"@ | Set-Content -Path $deskCmd -Encoding ASCII
@"
@echo off
rem ListingAssistants Playbook Show - all 24 playbooks on synthetic data (playbook-show\)
start "" powershell -NoProfile -WindowStyle Hidden -Command "for ($i = 0; $i -lt 90; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8766/ | Out-Null; break } catch { Start-Sleep -Seconds 1 } }; Start-Process http://127.0.0.1:8766/"
"%~dp0venv\Scripts\python.exe" "%~dp0app\tools\desk.py" --playbooks --state-dir "%~dp0playbook-show" --port 8766
if errorlevel 1 (echo. & echo The playbook show stopped with the error above. & pause)
"@ | Set-Content -Path $showCmd -Encoding ASCII
if ($env:LA_NO_SHORTCUTS -ne "1") {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shell = New-Object -ComObject WScript.Shell
    foreach ($pair in @(@("ListingAssistants Desk", $deskCmd), @("ListingAssistants Playbook Show", $showCmd))) {
        $lnk = $shell.CreateShortcut((Join-Path $desktop ($pair[0] + ".lnk")))
        $lnk.TargetPath = $pair[1]
        $lnk.WorkingDirectory = $LaHome
        $lnk.Save()
        Say "shortcut: $($pair[0])"
    }
}

# --- 6. Hermes (owner decision 2026-10-22: Hermes first) ------------------------
# The assistant works inside your running Broker Desk, on your records; it
# can read the desk and bring in an inquiry, and it never signs. This adds
# the server to Hermes' settings when Hermes is installed (a copy of the old
# settings is kept next to them), and always saves the block here.
Step "6/6 Hermes"
function YamlQuote($v) { "'" + ($v -replace "'", "''") + "'" }   # a ' in a folder name is doubled
function HermesEntry($indent) {
    $i = " " * $indent
    @(
        "${i}listingassistants:",
        "${i}  command: $(YamlQuote $Py)",
        "${i}  args: ['-m', 'dispatcher.identity_mcp']",
        "${i}  enabled: true",
        "${i}  env:",
        "${i}    IDENTITY_ROOT: $(YamlQuote $App)",
        "${i}    PYTHONPATH: $(YamlQuote $App)",
        "${i}    LISTINGASSISTANTS_STATE_DIR: $(YamlQuote $State)"
    ) -join "`n"
}
$snippet = Join-Path $LaHome "hermes-mcp.yaml"
$utf8 = New-Object System.Text.UTF8Encoding($false)    # no byte-order mark: YAML readers trip on it
[System.IO.File]::WriteAllText($snippet, ("mcp_servers:`n" + (HermesEntry 2) + "`n"), $utf8)
$hermesHomes = @($env:HERMES_HOME, (Join-Path $env:LOCALAPPDATA "hermes"), (Join-Path $env:USERPROFILE ".hermes")) |
    Where-Object { $_ -and (Test-Path (Join-Path $_ "config.yaml")) }
$cfg = if ($hermesHomes) { Join-Path @($hermesHomes)[0] "config.yaml" } else { $null }
if ($env:LA_NO_HERMES -eq "1") { $cfg = $null; Say "Hermes left alone (LA_NO_HERMES=1)" }
if (-not $cfg) {
    Say "Hermes settings not found. To add ListingAssistants to Hermes later, put the"
    Say "block in $snippet under mcp_servers: in Hermes' config.yaml"
} else {
    $text = [System.IO.File]::ReadAllText($cfg)
    $block = [regex]::Match($text, '(?m)^mcp_servers:[ \t]*\r?$')
    $backup = $cfg + ".bak-listingassistants"
    if ($text -match '(?m)^[ \t]+listingassistants:[ \t]*\r?$') {
        Say "Hermes already has a ListingAssistants entry ($cfg); left as it is."
        Say "If it names another folder, replace it with the block in $snippet"
    } elseif ($block.Success) {
        # the new entry goes first under mcp_servers:, indented like the
        # entries already there (2 spaces when there are none)
        $after = $text.Substring($block.Index + $block.Length)
        $first = [regex]::Match($after, '(?m)^([ \t]+)[^ \t\r\n#]')
        $next = [regex]::Match($after, '(?m)^[^ \t\r\n#]')          # the next top-level key
        $indent = if ($first.Success -and (-not $next.Success -or $first.Index -lt $next.Index)) { $first.Groups[1].Value.Length } else { 2 }
        Copy-Item $cfg $backup -Force
        $text = $text.Substring(0, $block.Index + $block.Length) + "`n" + (HermesEntry $indent) + $after
        [System.IO.File]::WriteAllText($cfg, $text, $utf8)
        Say "added to Hermes: $cfg (old copy: $backup)"
    } elseif ($text -match '(?m)^mcp_servers:') {
        Say "Hermes' mcp_servers is written on one line in $cfg; not changed."
        Say "Add the block in $snippet there yourself."
    } else {
        Copy-Item $cfg $backup -Force
        $sep = if ($text.EndsWith("`n") -or $text.Length -eq 0) { "" } else { "`n" }
        [System.IO.File]::WriteAllText($cfg, ($text + $sep + "mcp_servers:`n" + (HermesEntry 2) + "`n"), $utf8)
        Say "added to Hermes: $cfg (old copy: $backup)"
    }
    Say "In Hermes: start the Desk first, then type /reload-mcp (or restart Hermes)."
}

Write-Host ""
Write-Host "ListingAssistants is installed." -ForegroundColor Green
Say "Your desk:          double-click 'ListingAssistants Desk' (or run $deskCmd)"
Say "The playbook show:  double-click 'ListingAssistants Playbook Show'"
Say "Your records:       $State"
Say "Nothing reaches the outside world yet: client messages, vendor bookings and ads"
Say "stop in the desk's Outbox, marked not sent."
