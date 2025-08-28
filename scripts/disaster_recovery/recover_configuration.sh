#!/bin/bash
# Configuration Recovery Script
# Part of InkedUp Trading Bot Disaster Recovery Plan
# Usage: ./recover_configuration.sh

set -e  # Exit on any error

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/disaster_recovery_config_${TIMESTAMP}.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== CONFIGURATION RECOVERY STARTED ==="
log "Recovery timestamp: $TIMESTAMP"

# Step 1: Check for configuration backup sources
log "Step 1: Checking for configuration backup sources..."

# Check for local backup
if [[ -f ".env.backup" ]]; then
    log "Found local configuration backup: .env.backup"
    RECOVERY_SOURCE="local"
elif [[ -f "backups/latest_config.zip" ]]; then
    log "Found archived configuration backup: backups/latest_config.zip"
    RECOVERY_SOURCE="archive"
else
    # Try to find latest configuration backup from backup system
    LATEST_CONFIG_BACKUP=$(find backups -name "backup_configuration_*.zip" | sort -r | head -1 2>/dev/null || true)
    if [[ -n "$LATEST_CONFIG_BACKUP" ]]; then
        log "Found backup system configuration: $LATEST_CONFIG_BACKUP"
        RECOVERY_SOURCE="backup_system"
    else
        log "ERROR: No configuration backup found!"
        log "Checked locations:"
        log "  - .env.backup (local backup)"
        log "  - backups/latest_config.zip (manual archive)"
        log "  - backups/backup_configuration_*.zip (automated backups)"
        exit 1
    fi
fi

# Step 2: Backup current configuration if it exists
log "Step 2: Backing up current configuration state..."
if [[ -f ".env" ]]; then
    cp .env ".env.corrupted.${TIMESTAMP}"
    log "Current .env backed up to: .env.corrupted.${TIMESTAMP}"
else
    log "No current .env file found"
fi

# Step 3: Restore configuration based on source
log "Step 3: Restoring configuration from $RECOVERY_SOURCE source..."

case $RECOVERY_SOURCE in
    "local")
        cp .env.backup .env
        log "Configuration restored from local backup"
        ;;
    "archive")
        unzip -q backups/latest_config.zip
        log "Configuration restored from archived backup"
        ;;
    "backup_system")
        # Extract backup ID from filename
        BACKUP_ID=$(basename "$LATEST_CONFIG_BACKUP" .zip)
        log "Restoring from backup system: $BACKUP_ID"
        
        # Use backup system to restore
        python -m inkedup_bot.cli backup-restore "$BACKUP_ID" --confirm > "/tmp/config_restore_${TIMESTAMP}.log" 2>&1
        if [[ $? -eq 0 ]]; then
            log "Configuration restored from backup system"
        else
            log "ERROR: Failed to restore from backup system"
            cat "/tmp/config_restore_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
            exit 1
        fi
        ;;
esac

# Step 4: Validate restored configuration
log "Step 4: Validating restored configuration..."
if python -c "from inkedup_bot.config import BotConfig; BotConfig()" > "/tmp/config_validation_${TIMESTAMP}.log" 2>&1; then
    log "Configuration validation: PASSED"
else
    log "ERROR: Configuration validation FAILED"
    log "Validation errors:"
    cat "/tmp/config_validation_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 5: Test critical configuration values
log "Step 5: Testing critical configuration values..."

# Check for required fields
VALIDATION_ERRORS=0

if ! grep -q "^PUBLIC_KEY=" .env 2>/dev/null; then
    log "ERROR: PUBLIC_KEY not found in configuration"
    ((VALIDATION_ERRORS++))
fi

if ! grep -q "^PRIVATE_KEY=" .env 2>/dev/null; then
    log "ERROR: PRIVATE_KEY not found in configuration"
    ((VALIDATION_ERRORS++))
fi

if ! grep -q "^DATABASE_URL=" .env 2>/dev/null; then
    log "ERROR: DATABASE_URL not found in configuration"
    ((VALIDATION_ERRORS++))
fi

if [[ $VALIDATION_ERRORS -gt 0 ]]; then
    log "ERROR: $VALIDATION_ERRORS critical configuration values missing"
    exit 1
fi

# Step 6: Create immediate backup of restored configuration
log "Step 6: Creating backup of restored configuration..."
cp .env ".env.restored.${TIMESTAMP}"
python -m inkedup_bot.cli backup-create --backup-type=configuration > "/tmp/config_backup_${TIMESTAMP}.log" 2>&1
if [[ $? -eq 0 ]]; then
    log "Post-recovery configuration backup created"
else
    log "WARNING: Failed to create post-recovery configuration backup"
    cat "/tmp/config_backup_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
fi

# Step 7: Test application with restored configuration
log "Step 7: Testing application with restored configuration..."
if timeout 30s python -m inkedup_bot.cli config > "/tmp/config_test_${TIMESTAMP}.log" 2>&1; then
    log "Application configuration test: PASSED"
else
    log "ERROR: Application configuration test FAILED"
    cat "/tmp/config_test_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    exit 1
fi

log "=== CONFIGURATION RECOVERY COMPLETED ==="
log "Configuration recovery successful. System ready for operation."

# Display summary
echo ""
echo "==============================================="
echo "CONFIGURATION RECOVERY SUMMARY"
echo "==============================================="
echo "Status: SUCCESS"
echo "Recovery Source: $RECOVERY_SOURCE"
echo "Backup Created: .env.restored.${TIMESTAMP}"
echo "Log File: $LOG_FILE"
echo "==============================================="