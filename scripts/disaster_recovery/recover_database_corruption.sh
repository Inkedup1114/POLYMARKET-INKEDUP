#!/bin/bash
# Database Corruption Recovery Script
# Part of InkedUp Trading Bot Disaster Recovery Plan
# Usage: ./recover_database_corruption.sh

set -e  # Exit on any error

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/disaster_recovery_db_corruption_${TIMESTAMP}.log"
BACKUP_DIR="backups"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== DATABASE CORRUPTION RECOVERY STARTED ==="
log "Recovery timestamp: $TIMESTAMP"
log "Log file: $LOG_FILE"

# Step 1: Stop all applications
log "Step 1: Stopping all trading bot processes..."
if pgrep -f "inkedup_bot" > /dev/null; then
    log "Found running trading bot processes, attempting graceful shutdown..."
    
    # Try graceful shutdown first
    timeout 30s python -m inkedup_bot.cli shutdown-status &>/dev/null || true
    
    # Force kill if still running
    if pgrep -f "inkedup_bot" > /dev/null; then
        log "Graceful shutdown timeout, force terminating processes..."
        pkill -9 -f "inkedup_bot" || true
    fi
    
    sleep 2
    log "All trading bot processes stopped"
else
    log "No running trading bot processes found"
fi

# Step 2: Backup corrupted database
log "Step 2: Backing up corrupted database..."
if [[ -f "bot_data.db" ]]; then
    CORRUPT_BACKUP="bot_data_corrupted_${TIMESTAMP}.db"
    cp bot_data.db "$CORRUPT_BACKUP"
    log "Corrupted database backed up to: $CORRUPT_BACKUP"
else
    log "WARNING: No database file found to backup"
fi

# Step 3: Check available backups
log "Step 3: Checking available backups..."
if [[ ! -d "$BACKUP_DIR" ]]; then
    log "ERROR: Backup directory $BACKUP_DIR not found!"
    log "Cannot proceed with recovery without backups"
    exit 1
fi

# Find the latest backup
LATEST_BACKUP=$(find "$BACKUP_DIR" -name "backup_full_*.db" -o -name "backup_full_*.zip" | sort -r | head -1)
if [[ -z "$LATEST_BACKUP" ]]; then
    log "ERROR: No database backups found in $BACKUP_DIR"
    log "Available files:"
    ls -la "$BACKUP_DIR" || true
    exit 1
fi

log "Latest backup found: $LATEST_BACKUP"

# Step 4: Restore from backup
log "Step 4: Restoring database from backup..."
if [[ "$LATEST_BACKUP" == *.zip ]]; then
    # Handle compressed backup
    log "Extracting compressed backup..."
    unzip -q "$LATEST_BACKUP" -d "/tmp/restore_${TIMESTAMP}/"
    EXTRACTED_DB=$(find "/tmp/restore_${TIMESTAMP}/" -name "*.db" -o -name "*.tmp" | head -1)
    
    if [[ -n "$EXTRACTED_DB" ]]; then
        cp "$EXTRACTED_DB" bot_data.db
        rm -rf "/tmp/restore_${TIMESTAMP}/"
        log "Database restored from compressed backup"
    else
        log "ERROR: No database file found in compressed backup"
        exit 1
    fi
else
    # Handle uncompressed backup
    cp "$LATEST_BACKUP" bot_data.db
    log "Database restored from uncompressed backup"
fi

# Step 5: Verify database integrity
log "Step 5: Verifying database integrity..."
INTEGRITY_CHECK=$(sqlite3 bot_data.db "PRAGMA integrity_check;" 2>&1 || echo "FAILED")
if [[ "$INTEGRITY_CHECK" == "ok" ]]; then
    log "Database integrity check: PASSED"
else
    log "ERROR: Database integrity check FAILED: $INTEGRITY_CHECK"
    exit 1
fi

# Step 6: Test application startup
log "Step 6: Testing application startup..."
if timeout 30s python -m inkedup_bot.cli health --detailed > "/tmp/health_check_${TIMESTAMP}.log" 2>&1; then
    log "Application health check: PASSED"
    log "Database recovery completed successfully!"
else
    log "ERROR: Application health check FAILED"
    log "Health check output:"
    cat "/tmp/health_check_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 7: Create immediate backup of restored database
log "Step 7: Creating backup of restored database..."
python -m inkedup_bot.cli backup-create --backup-type=full > "/tmp/backup_restore_${TIMESTAMP}.log" 2>&1
if [[ $? -eq 0 ]]; then
    log "Post-recovery backup created successfully"
else
    log "WARNING: Failed to create post-recovery backup"
    cat "/tmp/backup_restore_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
fi

log "=== DATABASE CORRUPTION RECOVERY COMPLETED ==="
log "Recovery successful. System ready for trading."
log "Log file saved: $LOG_FILE"

# Display summary
echo ""
echo "==============================================="
echo "DATABASE CORRUPTION RECOVERY SUMMARY"
echo "==============================================="
echo "Status: SUCCESS"
echo "Recovery Time: $(($(date +%s) - $(date -d "1 minute ago" +%s))) seconds"
echo "Backup Used: $LATEST_BACKUP"
echo "Log File: $LOG_FILE"
echo "==============================================="