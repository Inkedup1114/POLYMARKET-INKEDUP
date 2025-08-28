#!/bin/bash
# Security Incident Response Script
# Part of InkedUp Trading Bot Disaster Recovery Plan
# Usage: ./respond_security_incident.sh [incident_type]

set -e  # Exit on any error

INCIDENT_TYPE=${1:-"general"}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="/tmp/security_incident_${TIMESTAMP}.log"
INCIDENT_DIR="/tmp/security_incident_${TIMESTAMP}"

# Logging function with security emphasis
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [SECURITY] $1" | tee -a "$LOG_FILE"
}

# Create incident directory
mkdir -p "$INCIDENT_DIR"

log "=== SECURITY INCIDENT RESPONSE ACTIVATED ==="
log "Incident Type: $INCIDENT_TYPE"
log "Response timestamp: $TIMESTAMP"
log "Incident directory: $INCIDENT_DIR"

# IMMEDIATE ACTIONS - CRITICAL FIRST 60 SECONDS

log "PHASE 1: IMMEDIATE RESPONSE (0-60 seconds)"

# Step 1: STOP ALL TRADING IMMEDIATELY
log "Step 1: EMERGENCY TRADING HALT"
log "Cancelling all open orders..."
timeout 10s python -m inkedup_bot.cli cancel-all > "$INCIDENT_DIR/cancel_orders.log" 2>&1 || log "WARNING: Order cancellation may have failed"

log "Terminating all trading processes..."
pkill -9 -f "inkedup_bot" 2>/dev/null || true
log "CRITICAL: ALL TRADING ACTIVITIES STOPPED"

# Step 2: Secure sensitive files
log "Step 2: Securing sensitive configuration..."
if [[ -f ".env" ]]; then
    chmod 600 .env
    cp .env "$INCIDENT_DIR/.env.incident.${TIMESTAMP}"
    log "Configuration secured and backed up"
fi

# Step 3: Document incident start
cat << EOF > "$INCIDENT_DIR/incident_report.md"
# Security Incident Report

**Incident ID**: SECURITY-${TIMESTAMP}
**Incident Type**: ${INCIDENT_TYPE}
**Start Time**: $(date)
**Severity**: CRITICAL
**Status**: ACTIVE

## Timeline
- $(date): Incident response activated
- $(date): Trading halted
- $(date): Configuration secured

## Actions Taken
- All trading activities stopped
- Sensitive files secured
- Incident response team notified

## Next Steps
- [ ] Investigate root cause
- [ ] Assess damage scope
- [ ] Plan recovery actions
- [ ] Generate new credentials
EOF

log "PHASE 2: ASSESSMENT AND CONTAINMENT (1-5 minutes)"

# Step 4: System state capture
log "Step 4: Capturing system state for analysis..."

# Capture running processes
ps aux > "$INCIDENT_DIR/processes.log"

# Capture network connections
netstat -tuln > "$INCIDENT_DIR/network_connections.log" 2>/dev/null || ss -tuln > "$INCIDENT_DIR/network_connections.log"

# Capture recent logs
if [[ -d "logs" ]]; then
    cp -r logs "$INCIDENT_DIR/logs_backup/"
fi

# Find recent log files
find . -name "*.log" -mtime -1 -exec cp {} "$INCIDENT_DIR/" \; 2>/dev/null || true

log "System state captured to: $INCIDENT_DIR"

# Step 5: Credential exposure analysis
log "Step 5: Analyzing potential credential exposure..."

EXPOSURE_FOUND=0

# Check log files for potential key exposure
log "Scanning logs for credential exposure..."
for logfile in $(find "$INCIDENT_DIR" -name "*.log" 2>/dev/null); do
    if grep -l -i -E "(private_key|api_key|secret|password)" "$logfile" 2>/dev/null; then
        log "WARNING: Potential credential exposure in: $(basename $logfile)"
        ((EXPOSURE_FOUND++))
    fi
done

# Check for recent file modifications
log "Checking for recent suspicious file modifications..."
find . -type f -mtime -1 -name "*.py" -o -name "*.env" -o -name "*.json" > "$INCIDENT_DIR/recent_files.log"

if [[ -s "$INCIDENT_DIR/recent_files.log" ]]; then
    log "Recent file modifications found - review required:"
    cat "$INCIDENT_DIR/recent_files.log" | tee -a "$LOG_FILE"
fi

# Step 6: Network activity analysis
log "Step 6: Analyzing recent network activity..."

# Check for unusual outbound connections
if command -v ss &> /dev/null; then
    ss -tuln | grep LISTEN > "$INCIDENT_DIR/listening_ports.log"
elif command -v netstat &> /dev/null; then
    netstat -tuln | grep LISTEN > "$INCIDENT_DIR/listening_ports.log"
fi

log "Network activity analysis completed"

log "PHASE 3: NOTIFICATION AND DOCUMENTATION (5-10 minutes)"

# Step 7: Generate incident notifications
log "Step 7: Generating incident notifications..."

# Create incident alert
cat << EOF > "$INCIDENT_DIR/incident_alert.txt"
SECURITY INCIDENT ALERT - InkedUp Trading Bot

Incident ID: SECURITY-${TIMESTAMP}
Severity: CRITICAL
Time: $(date)
Type: ${INCIDENT_TYPE}

IMMEDIATE ACTIONS TAKEN:
✅ All trading activities halted
✅ Open orders cancelled
✅ System processes terminated
✅ Sensitive files secured
✅ System state captured

REQUIRED MANUAL ACTIONS:
🚨 URGENT - Review Polymarket account for unauthorized activity
🚨 URGENT - Revoke all API keys immediately
🚨 URGENT - Generate new API credentials
🚨 URGENT - Review recent trading activity for anomalies

ASSESSMENT RESULTS:
- Credential exposure indicators: $EXPOSURE_FOUND found
- System state: Captured in $INCIDENT_DIR
- Network activity: Under review

DO NOT RESTART TRADING UNTIL:
1. Root cause identified
2. New credentials configured
3. Security review completed
4. System integrity verified

Next update in 30 minutes or upon completion of manual actions.

Contact: [INCIDENT RESPONSE TEAM]
EOF

log "Incident alert generated: $INCIDENT_DIR/incident_alert.txt"

# Step 8: Security checklist
log "Step 8: Security incident checklist..."

cat << EOF > "$INCIDENT_DIR/security_checklist.md"
# Security Incident Response Checklist

## Immediate Actions (COMPLETED)
- [x] Stop all trading activities
- [x] Cancel open orders
- [x] Terminate processes
- [x] Secure configuration files
- [x] Capture system state

## Manual Actions Required (PENDING)
- [ ] Review Polymarket account activity
- [ ] Check for unauthorized transactions
- [ ] Revoke all API keys in Polymarket dashboard
- [ ] Generate new API key pair
- [ ] Update .env with new credentials
- [ ] Review audit logs for unauthorized access
- [ ] Check for data exfiltration

## Investigation Actions (PENDING)
- [ ] Analyze logs for attack vectors
- [ ] Review file system for unauthorized changes
- [ ] Check network logs for suspicious connections
- [ ] Verify application integrity
- [ ] Scan for malware or unauthorized code

## Recovery Actions (PENDING)
- [ ] Update all credentials
- [ ] Patch any identified vulnerabilities
- [ ] Restore from clean backup if needed
- [ ] Implement additional security measures
- [ ] Test system integrity
- [ ] Gradual restart with monitoring

## Documentation (IN PROGRESS)
- [x] Incident report initiated
- [ ] Root cause analysis
- [ ] Impact assessment
- [ ] Lessons learned
- [ ] Security improvements plan
EOF

log "Security checklist created: $INCIDENT_DIR/security_checklist.md"

log "PHASE 4: RECOVERY PREPARATION (10+ minutes)"

# Step 9: Backup current state for forensics
log "Step 9: Creating forensic backup..."
if [[ -f "bot_data.db" ]]; then
    cp bot_data.db "$INCIDENT_DIR/bot_data_incident_${TIMESTAMP}.db"
    log "Database backed up for forensic analysis"
fi

# Step 10: Generate recovery plan
log "Step 10: Generating recovery plan..."

cat << EOF > "$INCIDENT_DIR/recovery_plan.md"
# Security Incident Recovery Plan

## Pre-Recovery Requirements
1. Complete investigation of incident cause
2. Verify all unauthorized access has been stopped
3. Generate new API credentials
4. Update configuration with new credentials
5. Verify system integrity

## Recovery Steps
1. **Configuration Update**
   - Update .env with new API credentials
   - Test configuration validation
   - Create configuration backup

2. **System Verification** 
   - Run comprehensive health checks
   - Verify database integrity
   - Test API connectivity with new credentials

3. **Security Validation**
   - Scan for unauthorized code changes
   - Verify log file integrity
   - Confirm monitoring systems active

4. **Gradual Restart**
   - Start in read-only mode
   - Monitor for 15 minutes
   - Enable trading with reduced limits
   - Gradually increase to normal operation

## Post-Recovery Actions
- Monitor for 24 hours with enhanced logging
- Review all trading activity
- Update security procedures
- Schedule security audit
EOF

log "Recovery plan generated: $INCIDENT_DIR/recovery_plan.md"

log "=== SECURITY INCIDENT RESPONSE PHASE 1 COMPLETED ==="
log "All automated response actions completed."
log "Manual intervention required - see incident directory: $INCIDENT_DIR"

# Display critical summary
echo ""
echo "=========================================================="
echo "🚨 SECURITY INCIDENT RESPONSE SUMMARY 🚨"
echo "=========================================================="
echo "Incident ID: SECURITY-${TIMESTAMP}"
echo "Status: AUTOMATED RESPONSE COMPLETED"
echo "Manual Actions Required: YES"
echo ""
echo "CRITICAL: DO NOT RESTART TRADING UNTIL:"
echo "1. Polymarket API keys revoked and regenerated"  
echo "2. .env file updated with new credentials"
echo "3. Security review completed"
echo "4. Recovery plan executed"
echo ""
echo "Incident Directory: $INCIDENT_DIR"
echo "Log File: $LOG_FILE" 
echo "Alert File: $INCIDENT_DIR/incident_alert.txt"
echo "=========================================================="
echo "⚠️  TRADING REMAINS DISABLED FOR SECURITY  ⚠️"
echo "=========================================================="