<#
.SYNOPSIS
  Start all AutoSocial AI FastAPI services from one terminal.

.DESCRIPTION
  Launches these services in separate windows/tabs:
    1. FastAPI server  (uvicorn, port 8036, --reload)
    2. Celery worker   (-P solo)
    3. Celery beat     (scheduler)
    4. Pinggy SSH tunnel (public URL -> localhost:8036)
    5. Local agent (optional, with -WithAgent)

  Each service runs in its own PowerShell window so logs are easy to read.

.PARAMETER WithAgent
  Also start the local agent (Terminal 4).

.PARAMETER WithTunnel
  Also start the Pinggy SSH tunnel. (Default = true; use -NoTunnel to skip.)

.PARAMETER Status
  Show what is currently running.

.PARAMETER Stop
  Stop all services started by this script.

.EXAMPLE
  .\start_all.ps1                  # FastAPI + Celery + tunnel
  .\start_all.ps1 -WithAgent       # everything including agent
  .\start_all.ps1 -Status          # check running services
  .\start_all.ps1 -Stop            # stop everything
#>

param(
    [switch]$WithAgent,
    [switch]$NoTunnel,
    [switch]$Status,
    [switch]$Stop
)

# ── Paths ────────────────────────────────────────────────────────────
$ProjectRoot  = "D:\RUNNING_PROJECT\Marketing-ira\Marketing-backend"
$VenvPython   = "$ProjectRoot\.venv\Scripts\python.exe"
$VenvCelery   = "$ProjectRoot\.venv\Scripts\celery.exe"
$AgentRoot    = "D:\RUNNING_PROJECT\AutoSocial_AI-main"
$AgentPython  = "$AgentRoot\.venv\Scripts\python.exe"

# PostgreSQL paths
$PgServiceName = "postgresql-x64-18"
$PgDataDir     = "C:\Program Files\PostgreSQL\18\data"
$PgBinDir      = "C:\Program Files\PostgreSQL\18\bin"

function Start-PostgreSQL {
    <#
      Ensures PostgreSQL is running before app services start.
      Tries the Windows service first; falls back to pg_ctl if the
      service account lacks permissions.
    #>
    $pgService = Get-Service -Name $PgServiceName -ErrorAction SilentlyContinue
    if ($pgService -and $pgService.Status -eq 'Running') {
        Write-Host "  [OK] PostgreSQL service is already running" -ForegroundColor Green
        return
    }

    Write-Host "  PostgreSQL is not running. Attempting to start..." -ForegroundColor Yellow

    # Try the Windows service first
    if ($pgService) {
        try {
            Start-Service -Name $PgServiceName -ErrorAction Stop
            Start-Sleep -Seconds 2
            if ((Get-Service -Name $PgServiceName).Status -eq 'Running') {
                Write-Host "  [OK] PostgreSQL service started" -ForegroundColor Green
                return
            }
        } catch {
            Write-Host "  Windows service start failed (permissions?). Trying pg_ctl..." -ForegroundColor Yellow
        }
    }

    # Fallback: start via pg_ctl directly
    $pgCtl = Join-Path $PgBinDir "pg_ctl.exe"
    if (Test-Path $pgCtl) {
        & $pgCtl status -D $PgDataDir 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] PostgreSQL is already running (pg_ctl)" -ForegroundColor Green
            return
        }
        $logFile = Join-Path $PgDataDir "log\auto_start.log"
        & $pgCtl start -D $PgDataDir -l $logFile -w 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        & $pgCtl status -D $PgDataDir 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] PostgreSQL started via pg_ctl" -ForegroundColor Green
        } else {
            Write-Host "  [FAIL] Could not start PostgreSQL! Check logs at $PgDataDir\log\" -ForegroundColor Red
            Write-Host "         Run this manually as Admin: Start-Service $PgServiceName" -ForegroundColor Red
        }
    } else {
        Write-Host "  [FAIL] pg_ctl.exe not found at $pgCtl" -ForegroundColor Red
    }
}

# Service tags used to track processes
$Services = @(
    @{ Name = "FastAPI";  Tag = "autosocial_fastapi";  Title = "FastAPI Server (port 8036)" }
    @{ Name = "Celery";      Tag = "autosocial_celery";       Title = "Celery Worker + Beat" }
    @{ Name = "Tunnel";   Tag = "autosocial_tunnel";   Title = "Pinggy SSH Tunnel" }
    @{ Name = "Agent";    Tag = "autosocial_agent";    Title = "Local Agent" }
)

function Get-ServiceProcess($tag) {
    Get-CimInstance Win32_Process -Filter "Name='powershell.exe' OR Name='python.exe' OR Name='ssh.exe'" |
        Where-Object { $_.CommandLine -like "*$tag*" }
}

function Show-Status {
    Write-Host "`n=== AutoSocial AI — Service Status ===" -ForegroundColor Cyan

    # Check PostgreSQL
    $pgService = Get-Service -Name $PgServiceName -ErrorAction SilentlyContinue
    if ($pgService -and $pgService.Status -eq 'Running') {
        Write-Host "  [RUNNING]  PostgreSQL      Service: $PgServiceName" -ForegroundColor Green
    } else {
        $pgCtl = Join-Path $PgBinDir "pg_ctl.exe"
        if (Test-Path $pgCtl) { & $pgCtl status -D $PgDataDir 2>&1 | Out-Null }
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [RUNNING]  PostgreSQL      (via pg_ctl)" -ForegroundColor Green
        } else {
            Write-Host "  [STOPPED]  PostgreSQL" -ForegroundColor Red
        }
    }

    foreach ($svc in $Services) {
        $procs = Get-ServiceProcess $svc.Tag
        if ($procs) {
            $pids = ($procs.ProcessId | Sort-Object -Unique) -join ", "
            Write-Host ("  [RUNNING]  {0,-14} PID(s): {1}" -f $svc.Name, $pids) -ForegroundColor Green
        } else {
            Write-Host ("  [STOPPED]  {0,-14}" -f $svc.Name) -ForegroundColor Red
        }
    }
    Write-Host ""
}

function Stop-AllServices {
    Write-Host "`nStopping all AutoSocial services..." -ForegroundColor Yellow
    foreach ($svc in $Services) {
        $procs = Get-ServiceProcess $svc.Tag
        foreach ($p in $procs) {
            try {
                Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
                Write-Host ("  Stopped {0} (PID {1})" -f $svc.Name, $p.ProcessId) -ForegroundColor Green
            } catch {
                Write-Host ("  Could not stop {0} (PID {1}): {2}" -f $svc.Name, $p.ProcessId, $_.Exception.Message) -ForegroundColor Red
            }
        }
    }
    Write-Host "Done.`n"
}

function Start-ServiceWindow($title, $tag, $command) {
    # Launch the command in a new PowerShell window, tagged with a unique marker
    # so we can find/kill it later. The marker is embedded in the window title.
    $marker = "[$tag]"
    $inner  = "`$Host.UI.RawUI.WindowTitle = '$marker $title'; $command"
    $psCmd  = @("-NoExit", "-Command", $inner)
    Start-Process powershell -ArgumentList $psCmd
    Write-Host ("  Started {0}  -> {1}" -f $title, $marker) -ForegroundColor Green
}

# ── Main ─────────────────────────────────────────────────────────────

if ($Status) { Show-Status; return }
if ($Stop)   { Stop-AllServices; return }

Write-Host "`n=== Starting AutoSocial AI services ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot`n"

# 0) Ensure PostgreSQL is running (app + Celery both need it)
Start-PostgreSQL
Write-Host ""

# Common env setup for child windows
$EnvSetup = "
Set-Location '$ProjectRoot'
`$env:PYTHONPATH = '.'
"

# 1) FastAPI server
$fastapiCmd = $EnvSetup + "& '$VenvPython' -m uvicorn src.main:app --host 0.0.0.0 --port 8036 --reload"
Start-ServiceWindow "FastAPI Server (port 8036)" "autosocial_fastapi" $fastapiCmd

# 2) Celery worker + beat (single process, -B runs beat embedded)
$celeryCmd = $EnvSetup + "& '$VenvCelery' -A src.core.celery_app worker -l info -P solo -B"
Start-ServiceWindow "Celery Worker + Beat" "autosocial_celery" $celeryCmd

# 3) Pinggy tunnel (unless -NoTunnel)
if (-not $NoTunnel) {
    $tunnelCmd = "while (`$true) { ssh -p 443 -R0:127.0.0.1:8036 -L127.0.0.1:4302:localhost:4300 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 WJH56A26uJc+force@ap.pro.pinggy.io; Start-Sleep -Seconds 10 }"
    Start-ServiceWindow "Pinggy SSH Tunnel" "autosocial_tunnel" $tunnelCmd
}

# 5) Local agent (optional)
if ($WithAgent) {
    $agentCmd = "Set-Location '$AgentRoot'; & '$AgentPython' local_agent\agent.py"
    Start-ServiceWindow "Local Agent" "autosocial_agent" $agentCmd
}

Write-Host "`nAll requested services started in separate windows." -ForegroundColor Cyan
Write-Host "Use: .\start_all.ps1 -Status  to check status"
Write-Host "Use: .\start_all.ps1 -Stop    to stop everything`n"