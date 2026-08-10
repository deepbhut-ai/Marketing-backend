@echo off
REM ============================================================
REM  AutoSocial AI - Start All Services (start_all.bat)
REM  Launches 4 services in separate windows:
REM    1. FastAPI Server  (port 8036, --reload)
REM    2. Celery Worker   (-P solo)
REM    3. Celery Beat     (scheduler)
REM    4. Pinggy SSH Tunnel (public URL -> 127.0.0.1:8036)
REM
REM  Usage:
REM    start_all.bat              = FastAPI + Celery + Tunnel
REM    start_all.bat agent       = also start local agent
REM    start_all.bat notunnel    = skip Pinggy tunnel
REM    start_all.bat status      = show running services
REM    start_all.bat stop        = stop all services
REM ============================================================

setlocal

set "PROJECT_ROOT=D:\RUNNING_PROJECT\Marketing-ira\Marketing-backend"
set "VENV_PY=%PROJECT_ROOT%\.venv\Scripts\python.exe"
set "VENV_CELERY=%PROJECT_ROOT%\.venv\Scripts\celery.exe"
set "AGENT_ROOT=D:\RUNNING_PROJECT\AutoSocial_AI-main"
set "AGENT_PY=%AGENT_ROOT%\.venv\Scripts\python.exe"
set "PG_SERVICE=postgresql-x64-18"
set "PG_BINDIR=C:\Program Files\PostgreSQL\18\bin"
set "PG_DATADIR=C:\Program Files\PostgreSQL\18\data"

REM ── Argument handling ───────────────────────────────────────
if /i "%1"=="status" goto :status
if /i "%1"=="stop"   goto :stop
if /i "%1"=="agent"   set "WITH_AGENT=1"
if /i "%1"=="notunnel" set "NO_TUNNEL=1"
if /i "%2"=="agent"   set "WITH_AGENT=1"
if /i "%2"=="notunnel" set "NO_TUNNEL=1"

echo.
echo === Starting AutoSocial AI services ===
echo Project root: %PROJECT_ROOT%
echo.

REM ── 0) Ensure PostgreSQL is running ────────────────────────
sc query %PG_SERVICE% | findstr "RUNNING" >nul 2>&1
if %errorlevel%==0 (
  echo   [OK] PostgreSQL service is already running
) else (
  echo   PostgreSQL is not running. Attempting to start...
  net start %PG_SERVICE% >nul 2>&1
  if !errorlevel!==0 (
    echo   [OK] PostgreSQL service started
  ) else (
    echo   Windows service start failed. Trying pg_ctl...
    "%PG_BINDIR%\pg_ctl.exe" status -D "%PG_DATADIR%" >nul 2>&1
    if !errorlevel!==0 (
      echo   [OK] PostgreSQL is already running ^(pg_ctl^)
    ) else (
      "%PG_BINDIR%\pg_ctl.exe" start -D "%PG_DATADIR%" -l "%PG_DATADIR%\log\auto_start.log" -w >nul 2>&1
      if !errorlevel!==0 (
        echo   [OK] PostgreSQL started via pg_ctl
      ) else (
        echo   [FAIL] Could not start PostgreSQL! Check logs at %PG_DATADIR%\log\
        echo          Run this manually as Admin: net start %PG_SERVICE%
      )
    )
  )
)
echo.

REM ── 1) FastAPI Server ───────────────────────────────────────
start "autosocial_fastapi - FastAPI Server (port 8036)" cmd /k ^
  "cd /d %PROJECT_ROOT% && set PYTHONPATH=. && "%VENV_PY%" -m uvicorn src.main:app --host 0.0.0.0 --port 8036 --reload"
echo   [STARTED] FastAPI Server (port 8036)

REM ── 2) Celery Worker + Beat (single process, -B runs beat embedded) ──
start "autosocial_celery - Celery Worker + Beat" cmd /k ^
  "cd /d %PROJECT_ROOT% && set PYTHONPATH=. && "%VENV_CELERY%" -A src.core.celery_app worker -l info -P solo -B"
echo   [STARTED] Celery Worker + Beat (single process)

REM ── 3) Pinggy SSH Tunnel ────────────────────────────────────
if defined NO_TUNNEL (
  echo   [SKIPPED] Pinggy Tunnel (-notunnel)
) else (
  start "autosocial_tunnel - Pinggy SSH Tunnel" cmd /k ^
    "ssh -p 443 -R0:127.0.0.1:8036 -L127.0.0.1:4302:localhost:4300 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 WJH56A26uJc+force@ap.pro.pinggy.io"
  echo   [STARTED] Pinggy SSH Tunnel
)

REM ── 5) Local Agent (optional) ───────────────────────────────
if defined WITH_AGENT (
  start "autosocial_agent - Local Agent" cmd /k ^
    "cd /d %AGENT_ROOT% && "%AGENT_PY%" local_agent\agent.py"
  echo   [STARTED] Local Agent
) else (
  echo   [SKIPPED] Local Agent (use 'start_all.bat agent' to include)
)

echo.
echo All requested services started in separate windows.
echo Use: start_all.bat status  to check status
echo Use: start_all.bat stop    to stop everything
echo.
goto :eof

REM ============================================================
REM  STATUS - show running services
REM ============================================================
:status
echo.
echo === AutoSocial AI - Service Status ===
echo.

echo   [PostgreSQL]
sc query %PG_SERVICE% | findstr "RUNNING" >nul 2>&1
if %errorlevel%==0 (echo     [RUNNING]) else (echo     [STOPPED])

echo   [FastAPI]    - port 8036
netstat -ano | findstr ":8036" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (echo     [RUNNING]) else (echo     [STOPPED])

echo   [Celery Worker+Beat]
tasklist /fi "imagename eq celery.exe" 2>nul | findstr "celery.exe" >nul 2>&1
if %errorlevel%==0 (echo     [RUNNING]) else (echo     [STOPPED])

echo   [Tunnel]
tasklist /fi "imagename eq ssh.exe" 2>nul | findstr "ssh.exe" >nul 2>&1
if %errorlevel%==0 (echo     [RUNNING]) else (echo     [STOPPED])

echo   [Agent]
tasklist /fi "windowtitle eq autosocial_agent*" 2>nul | findstr "cmd.exe" >nul 2>&1
if %errorlevel%==0 (echo     [RUNNING]) else (echo     [STOPPED])

echo.
goto :eof

REM ============================================================
REM  STOP - kill all services by window title marker
REM ============================================================
:stop
echo.
echo Stopping all AutoSocial services...
echo.

REM Kill windows by their title markers
taskkill /fi "windowtitle eq autosocial_fastapi*" /f >nul 2>&1
taskkill /fi "windowtitle eq autosocial_celery*" /f >nul 2>&1
taskkill /fi "windowtitle eq autosocial_tunnel*" /f >nul 2>&1
taskkill /fi "windowtitle eq autosocial_agent*" /f >nul 2>&1

REM Also kill any celery/uvicorn processes tied to our venv
taskkill /fi "imagename eq celery.exe" /f >nul 2>&1

echo   Done. All services stopped.
echo.
goto :eof