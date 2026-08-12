@echo off
REM ============================================================
REM  PostgreSQL Database Backup Script (Windows)
REM  Database: zetta_social
REM  Usage:    backup_db.bat
REM ============================================================
setlocal

cd /d "%~dp0"

REM ── Config ──────────────────────────────────────────────────────
set DB_NAME=zetta_social
set DB_USER=postgres
set DB_HOST=localhost
set DB_PORT=5432
set BACKUP_DIR=backups

REM ── Timestamp ───────────────────────────────────────────────────
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set YYYY=%dt:~0,4%
set MM=%dt:~4,2%
set DD=%dt:~6,2%
set HH=%dt:~8,2%
set MIN=%dt:~10,2%
set SS=%dt:~12,2%
set TIMESTAMP=%YYYY%%MM%%DD%_%HH%%MIN%%SS%

set BACKUP_FILE=%BACKUP_DIR%\%DB_NAME%_%TIMESTAMP%.sql

REM ── Create backup directory ─────────────────────────────────────
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

echo.
echo ========================================
echo  PostgreSQL Database Backup
echo ========================================
echo.
echo [INFO] Database: %DB_NAME%
echo [INFO] Backup file: %BACKUP_FILE%
echo.

REM ── Backup ──────────────────────────────────────────────────────
set PGPASSWORD=root
pg_dump -U %DB_USER% -h %DB_HOST% -p %DB_PORT% -d %DB_NAME% --no-owner --no-privileges --format=plain -f "%BACKUP_FILE%"

if errorlevel 1 (
    echo.
    echo [ERROR] Backup failed!
    exit /b 1
)

echo.
echo ========================================
echo  Backup complete!
echo ========================================
echo.
echo  File: %BACKUP_FILE%
echo.

endlocal