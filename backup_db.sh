#!/usr/bin/env bash
# ============================================================
#  PostgreSQL Database Backup Script
#  Database: zetta_social
#  Usage:    ./backup_db.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"

# ── Config ────────────────────────────────────────────────────────
DB_NAME="zetta_social"
DB_USER="postgres"
DB_HOST="localhost"
DB_PORT="5432"
BACKUP_DIR="backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.sql"

# ── Create backup directory ───────────────────────────────────────
mkdir -p "$BACKUP_DIR"

# ── Backup ────────────────────────────────────────────────────────
echo "========================================"
echo "  PostgreSQL Database Backup"
echo "========================================"
echo ""
echo "[INFO] Database: $DB_NAME"
echo "[INFO] Backup file: $BACKUP_FILE"
echo ""

PGPASSWORD="root" pg_dump \
    -U "$DB_USER" \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -d "$DB_NAME" \
    --no-owner \
    --no-privileges \
    --format=plain \
    -f "$BACKUP_FILE"

# ── Compress ──────────────────────────────────────────────────────
gzip "$BACKUP_FILE"
COMPRESSED="${BACKUP_FILE}.gz"

FILE_SIZE=$(du -h "$COMPRESSED" | cut -f1)

echo ""
echo "========================================"
echo "  Backup complete!"
echo "========================================"
echo ""
echo "  File: $COMPRESSED"
echo "  Size: $FILE_SIZE"
echo ""

# ── Keep only last 10 backups ─────────────────────────────────────
BACKUP_COUNT=$(ls -1 "${BACKUP_DIR}"/${DB_NAME}_*.sql.gz 2>/dev/null | wc -l)
MAX_BACKUPS=10

if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    echo "[INFO] Keeping only last $MAX_BACKUPS backups..."
    ls -1t "${BACKUP_DIR}"/${DB_NAME}_*.sql.gz | tail -n +$((MAX_BACKUPS + 1)) | xargs rm -f
    echo "[OK] Old backups removed"
fi

echo ""
echo "[OK] Done!"