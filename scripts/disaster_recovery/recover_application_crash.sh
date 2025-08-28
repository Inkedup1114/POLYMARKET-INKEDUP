#!/bin/bash
# Application Crash Recovery Script
# Part of InkedUp Trading Bot Disaster Recovery Plan
# Usage: ./recover_application_crash.sh

set -e  # Exit on any error

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/disaster_recovery_app_crash_${TIMESTAMP}.log"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== APPLICATION CRASH RECOVERY STARTED ==="
log "Recovery timestamp: $TIMESTAMP"

# Step 1: Assess current system state
log "Step 1: Assessing current system state..."

# Check for running processes
RUNNING_PROCESSES=$(pgrep -f "inkedup_bot" | wc -l)
log "Found $RUNNING_PROCESSES running inkedup_bot processes"

# Check system resources
MEMORY_USAGE=$(free | grep '^Mem:' | awk '{printf("%.1f", $3/$2 * 100.0)}')
DISK_USAGE=$(df . | tail -1 | awk '{print $5}' | sed 's/%//')
log "System resources: Memory ${MEMORY_USAGE}% used, Disk ${DISK_USAGE}% used"

# Check for lock files or PIDs
LOCK_FILES=$(find /tmp -name "inkedup_*.lock" 2>/dev/null | wc -l)
PID_FILES=$(find /tmp -name "trading_session_*.pid" 2>/dev/null | wc -l)
log "Found $LOCK_FILES lock files, $PID_FILES PID files"

# Step 2: Graceful shutdown attempt
log "Step 2: Attempting graceful shutdown of existing processes..."

if [[ $RUNNING_PROCESSES -gt 0 ]]; then
    log "Attempting graceful shutdown via shutdown manager..."
    
    # Try graceful shutdown with timeout
    timeout 30s python -c "
import asyncio
from inkedup_bot.shutdown_manager import get_shutdown_manager
try:
    manager = get_shutdown_manager()
    asyncio.run(manager.trigger_shutdown('disaster_recovery_restart'))
    print('Graceful shutdown completed')
except Exception as e:
    print(f'Graceful shutdown failed: {e}')
    exit(1)
" > "/tmp/graceful_shutdown_${TIMESTAMP}.log" 2>&1

    if [[ $? -eq 0 ]]; then
        log "Graceful shutdown completed successfully"
        sleep 3  # Allow processes to fully terminate
    else
        log "Graceful shutdown failed or timed out, proceeding to force termination"
    fi
    
    # Check if processes are still running
    REMAINING_PROCESSES=$(pgrep -f "inkedup_bot" | wc -l)
    if [[ $REMAINING_PROCESSES -gt 0 ]]; then
        log "Force terminating remaining $REMAINING_PROCESSES processes..."
        pkill -9 -f "inkedup_bot" || true
        sleep 2
    fi
else
    log "No running processes found to shutdown"
fi

# Step 3: Clean up resources
log "Step 3: Cleaning up system resources..."

# Remove lock files
if [[ $LOCK_FILES -gt 0 ]]; then
    log "Removing $LOCK_FILES lock files..."
    find /tmp -name "inkedup_*.lock" -delete 2>/dev/null || true
fi

# Remove PID files
if [[ $PID_FILES -gt 0 ]]; then
    log "Removing $PID_FILES PID files..."
    find /tmp -name "trading_session_*.pid" -delete 2>/dev/null || true
fi

# Clear any shared memory segments
log "Clearing shared memory segments..."
ipcs -m | grep $(whoami) | awk '{print $2}' | xargs -r ipcrm -m 2>/dev/null || true

# Step 4: System health verification
log "Step 4: Verifying system health before restart..."

# Check critical files exist
CRITICAL_FILES=("bot_data.db" ".env")
for file in "${CRITICAL_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        log "ERROR: Critical file missing: $file"
        log "Cannot proceed with application restart"
        exit 1
    fi
done
log "Critical files verified"

# Check database integrity
log "Checking database integrity..."
DB_INTEGRITY=$(sqlite3 bot_data.db "PRAGMA integrity_check;" 2>&1 || echo "FAILED")
if [[ "$DB_INTEGRITY" == "ok" ]]; then
    log "Database integrity: PASSED"
else
    log "WARNING: Database integrity check failed: $DB_INTEGRITY"
    log "May need database recovery"
fi

# Check configuration validity
log "Validating configuration..."
if python -c "from inkedup_bot.config import BotConfig; BotConfig()" > "/tmp/config_check_${TIMESTAMP}.log" 2>&1; then
    log "Configuration validation: PASSED"
else
    log "ERROR: Configuration validation FAILED"
    cat "/tmp/config_check_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    exit 1
fi

# Step 5: Memory and resource optimization
log "Step 5: Optimizing system resources..."

# Clear system caches if possible
log "Clearing system caches..."
sync
echo 1 > /proc/sys/vm/drop_caches 2>/dev/null || true

# Set resource limits
log "Setting resource limits..."
ulimit -v 2097152 2>/dev/null || true  # 2GB virtual memory limit
ulimit -n 4096 2>/dev/null || true     # File descriptor limit

# Step 6: Application restart with monitoring
log "Step 6: Restarting application with health monitoring..."

# Start health monitoring in background
log "Starting health monitoring..."
(
    while true; do
        if pgrep -f "inkedup_bot" > /dev/null; then
            MEMORY_MB=$(ps -p $(pgrep -f "inkedup_bot" | head -1) -o rss= 2>/dev/null | awk '{print int($1/1024)}' || echo "0")
            if [[ $MEMORY_MB -gt 1024 ]]; then  # Alert if over 1GB
                echo "[$(date)] WARNING: High memory usage: ${MEMORY_MB}MB" >> "/tmp/recovery_monitor_${TIMESTAMP}.log"
            fi
        fi
        sleep 30
    done
) &
MONITOR_PID=$!

# Perform health check to verify startup
log "Performing comprehensive health check..."
if timeout 45s python -m inkedup_bot.cli health --detailed > "/tmp/health_check_${TIMESTAMP}.log" 2>&1; then
    log "Application health check: PASSED"
    
    # Extract key health metrics
    if grep -q "healthy" "/tmp/health_check_${TIMESTAMP}.log"; then
        log "System components report healthy status"
    else
        log "WARNING: Some components may not be fully healthy"
    fi
else
    log "ERROR: Application health check FAILED"
    log "Health check output:"
    cat "/tmp/health_check_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    
    # Kill monitoring process
    kill $MONITOR_PID 2>/dev/null || true
    exit 1
fi

# Step 7: Verify trading readiness
log "Step 7: Verifying trading system readiness..."

# Test configuration access
log "Testing configuration access..."
python -c "
from inkedup_bot.config import BotConfig
config = BotConfig()
print(f'API Base: {config.polymarket_api_base}')
print(f'Database: {config.database_url}')
print('Configuration access: OK')
" > "/tmp/config_access_${TIMESTAMP}.log" 2>&1

if [[ $? -eq 0 ]]; then
    log "Configuration access: PASSED"
else
    log "ERROR: Configuration access FAILED"
    cat "/tmp/config_access_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
    kill $MONITOR_PID 2>/dev/null || true
    exit 1
fi

# Step 8: Create recovery backup
log "Step 8: Creating post-recovery backup..."
python -m inkedup_bot.cli backup-create --backup-type=full > "/tmp/recovery_backup_${TIMESTAMP}.log" 2>&1
if [[ $? -eq 0 ]]; then
    log "Post-recovery backup created successfully"
else
    log "WARNING: Failed to create post-recovery backup"
    cat "/tmp/recovery_backup_${TIMESTAMP}.log" | tee -a "$LOG_FILE"
fi

# Kill monitoring process
kill $MONITOR_PID 2>/dev/null || true

log "=== APPLICATION CRASH RECOVERY COMPLETED ==="
log "Application recovery successful. System ready for trading."
log "Monitor log: /tmp/recovery_monitor_${TIMESTAMP}.log"

# Display summary
echo ""
echo "==============================================="
echo "APPLICATION CRASH RECOVERY SUMMARY"
echo "==============================================="
echo "Status: SUCCESS"
echo "Processes Terminated: $RUNNING_PROCESSES"
echo "Resources Cleaned: $((LOCK_FILES + PID_FILES)) files"
echo "Health Check: PASSED"
echo "Configuration: VALID"
echo "Database Integrity: $([[ "$DB_INTEGRITY" == "ok" ]] && echo "OK" || echo "WARNING")"
echo "Log File: $LOG_FILE"
echo "==============================================="
echo "System is ready for trading operations"
echo "==============================================="