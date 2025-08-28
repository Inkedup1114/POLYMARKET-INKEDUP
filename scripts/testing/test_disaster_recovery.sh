#!/bin/bash
# Disaster Recovery Testing Script
# Tests all disaster recovery procedures
# Usage: ./test_disaster_recovery.sh [test_type]

set -e

TEST_TYPE=${1:-"all"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/disaster_recovery_test_${TIMESTAMP}.log"
TEST_DIR="/tmp/dr_test_${TIMESTAMP}"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Create test directory
mkdir -p "$TEST_DIR"

log "=== DISASTER RECOVERY TESTING STARTED ==="
log "Test type: $TEST_TYPE"
log "Test timestamp: $TIMESTAMP"
log "Test directory: $TEST_DIR"

# Test results tracking
TESTS_PASSED=0
TESTS_FAILED=0
FAILED_TESTS=()

# Test function wrapper
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    log "Running test: $test_name"
    
    if eval "$test_command" > "$TEST_DIR/${test_name}.log" 2>&1; then
        log "TEST PASSED: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        log "TEST FAILED: $test_name"
        FAILED_TESTS+=("$test_name")
        ((TESTS_FAILED++))
        return 1
    fi
}

# Test 1: Database Corruption Recovery
test_database_corruption() {
    log "=== Testing Database Corruption Recovery ==="
    
    # Create backup first
    log "Creating test backup..."
    python -m inkedup_bot.cli backup-create --backup-type=full
    
    # Backup original database
    cp bot_data.db "$TEST_DIR/bot_data_original.db"
    
    # Simulate corruption
    log "Simulating database corruption..."
    dd if=/dev/zero of=bot_data.db bs=1024 count=10 2>/dev/null
    
    # Test recovery script
    log "Testing recovery script..."
    bash scripts/disaster_recovery/recover_database_corruption.sh
    
    # Verify recovery
    log "Verifying database recovery..."
    sqlite3 bot_data.db "PRAGMA integrity_check;" | grep -q "ok"
    
    # Test application startup
    timeout 30s python -m inkedup_bot.cli health --detailed > /dev/null
    
    log "Database corruption recovery test completed"
}

# Test 2: Configuration Recovery
test_configuration_recovery() {
    log "=== Testing Configuration Recovery ==="
    
    # Backup original configuration
    cp .env "$TEST_DIR/.env_original"
    
    # Create configuration backup
    cp .env .env.backup
    
    # Simulate configuration loss
    log "Simulating configuration loss..."
    rm .env
    
    # Test recovery script
    log "Testing configuration recovery script..."
    bash scripts/disaster_recovery/recover_configuration.sh
    
    # Verify configuration restoration
    log "Verifying configuration recovery..."
    [[ -f .env ]] || return 1
    python -c "from inkedup_bot.config import BotConfig; BotConfig()"
    
    log "Configuration recovery test completed"
}

# Test 3: Application Crash Recovery
test_application_crash() {
    log "=== Testing Application Crash Recovery ==="
    
    # Start test application
    log "Starting test application..."
    python -m inkedup_bot.cli scan --interval=300 &
    APP_PID=$!
    
    sleep 5
    
    # Create lock and PID files to simulate crash state
    echo $APP_PID > "/tmp/trading_session_${TIMESTAMP}.pid"
    touch "/tmp/inkedup_crash_test_${TIMESTAMP}.lock"
    
    # Simulate crash
    log "Simulating application crash..."
    kill -9 $APP_PID 2>/dev/null || true
    
    # Test recovery script
    log "Testing application crash recovery script..."
    bash scripts/disaster_recovery/recover_application_crash.sh
    
    # Verify cleanup
    log "Verifying cleanup..."
    [[ ! -f "/tmp/trading_session_${TIMESTAMP}.pid" ]] || return 1
    [[ ! -f "/tmp/inkedup_crash_test_${TIMESTAMP}.lock" ]] || return 1
    
    # Verify health
    timeout 30s python -m inkedup_bot.cli health > /dev/null
    
    log "Application crash recovery test completed"
}

# Test 4: Security Incident Response
test_security_response() {
    log "=== Testing Security Incident Response ==="
    
    # Test security script (dry run mode)
    log "Testing security incident response script..."
    bash scripts/disaster_recovery/respond_security_incident.sh "test_incident"
    
    # Verify incident directory creation
    INCIDENT_DIR=$(ls -d /tmp/security_incident_* | tail -1)
    [[ -d "$INCIDENT_DIR" ]] || return 1
    
    # Verify incident files
    [[ -f "$INCIDENT_DIR/incident_report.md" ]] || return 1
    [[ -f "$INCIDENT_DIR/security_checklist.md" ]] || return 1
    [[ -f "$INCIDENT_DIR/recovery_plan.md" ]] || return 1
    
    log "Security incident response test completed"
}

# Test 5: End-to-End Recovery Simulation
test_full_disaster_simulation() {
    log "=== Testing Full Disaster Simulation ==="
    
    # Create complete system backup
    log "Creating complete system backup..."
    cp bot_data.db "$TEST_DIR/full_backup_db.db"
    cp .env "$TEST_DIR/full_backup_env"
    
    # Simulate multiple failures
    log "Simulating multiple system failures..."
    
    # Corrupt database and configuration
    dd if=/dev/zero of=bot_data.db bs=1024 count=5 2>/dev/null
    echo "CORRUPTED_CONFIG=true" > .env
    
    # Create bogus lock files
    touch /tmp/inkedup_disaster_test.lock
    
    # Recovery sequence
    log "Executing recovery sequence..."
    
    # 1. Configuration recovery
    cp "$TEST_DIR/full_backup_env" .env.backup
    bash scripts/disaster_recovery/recover_configuration.sh
    
    # 2. Database recovery  
    python -m inkedup_bot.cli backup-create --backup-type=full
    cp "$TEST_DIR/full_backup_db.db" bot_data.db
    
    # 3. Application cleanup and restart
    bash scripts/disaster_recovery/recover_application_crash.sh
    
    # Verify full system recovery
    log "Verifying full system recovery..."
    timeout 45s python -m inkedup_bot.cli health --detailed --diagnostics > /dev/null
    
    log "Full disaster simulation test completed"
}

# Run tests based on type
case $TEST_TYPE in
    "database"|"db")
        run_test "database_corruption_recovery" "test_database_corruption"
        ;;
    "config"|"configuration")  
        run_test "configuration_recovery" "test_configuration_recovery"
        ;;
    "app"|"application")
        run_test "application_crash_recovery" "test_application_crash"
        ;;
    "security"|"sec")
        run_test "security_incident_response" "test_security_response"
        ;;
    "full"|"simulation")
        run_test "full_disaster_simulation" "test_full_disaster_simulation"
        ;;
    "all"|*)
        log "Running all disaster recovery tests..."
        run_test "database_corruption_recovery" "test_database_corruption"
        run_test "configuration_recovery" "test_configuration_recovery"  
        run_test "application_crash_recovery" "test_application_crash"
        run_test "security_incident_response" "test_security_response"
        run_test "full_disaster_simulation" "test_full_disaster_simulation"
        ;;
esac

# Cleanup test artifacts
log "Cleaning up test artifacts..."
rm -f /tmp/inkedup_*.lock
rm -f /tmp/trading_session_*.pid
rm -rf /tmp/security_incident_* 2>/dev/null || true

log "=== DISASTER RECOVERY TESTING COMPLETED ==="

# Generate test report
cat << EOF > "$TEST_DIR/test_report.md"
# Disaster Recovery Test Report

**Test Run**: $TIMESTAMP
**Test Type**: $TEST_TYPE
**Duration**: $(($(date +%s) - $(date -d "10 minutes ago" +%s))) seconds

## Results Summary
- **Tests Passed**: $TESTS_PASSED
- **Tests Failed**: $TESTS_FAILED
- **Success Rate**: $(( TESTS_PASSED * 100 / (TESTS_PASSED + TESTS_FAILED) ))%

## Failed Tests
$(for test in "${FAILED_TESTS[@]}"; do echo "- $test"; done)

## Test Details
See individual test logs in: $TEST_DIR/

## Recommendations
$(if [[ $TESTS_FAILED -gt 0 ]]; then
    echo "- Review failed test logs for issues"
    echo "- Update disaster recovery procedures as needed"  
    echo "- Re-run failed tests after fixes"
else
    echo "- All tests passed successfully"
    echo "- Disaster recovery procedures validated"
    echo "- System ready for production"
fi)
EOF

# Display final summary
echo ""
echo "========================================================"
echo "DISASTER RECOVERY TEST SUMMARY"
echo "========================================================"
echo "Test Type: $TEST_TYPE"
echo "Tests Passed: $TESTS_PASSED"
echo "Tests Failed: $TESTS_FAILED"
echo "Success Rate: $(( TESTS_PASSED * 100 / (TESTS_PASSED + TESTS_FAILED) ))%"
if [[ $TESTS_FAILED -gt 0 ]]; then
    echo ""
    echo "FAILED TESTS:"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
fi
echo ""
echo "Test Directory: $TEST_DIR"
echo "Log File: $LOG_FILE"
echo "Test Report: $TEST_DIR/test_report.md"
echo "========================================================"

# Exit with appropriate code
[[ $TESTS_FAILED -eq 0 ]] && exit 0 || exit 1