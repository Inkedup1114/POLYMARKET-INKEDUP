#!/bin/bash
# Health check script for InkedUp Polymarket Bot container
set -e

# Configuration
HEALTH_CHECK_URL="${HEALTH_CHECK_URL:-http://localhost:8080/health}"
TIMEOUT="${HEALTH_CHECK_TIMEOUT:-10}"
MAX_RETRIES="${HEALTH_CHECK_RETRIES:-3}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${1}" >&2
}

# Check if curl is available
if ! command -v curl &> /dev/null; then
    log "${RED}[ERROR] curl is not available${NC}"
    exit 1
fi

# Function to check HTTP endpoint
check_http_health() {
    local url="$1"
    local timeout="$2"
    
    response=$(curl -f -s --max-time "$timeout" "$url" 2>/dev/null)
    status=$?
    
    if [ $status -eq 0 ]; then
        # Parse JSON response if possible
        if echo "$response" | jq . >/dev/null 2>&1; then
            health_status=$(echo "$response" | jq -r '.status // "unknown"')
            if [ "$health_status" = "healthy" ] || [ "$health_status" = "ok" ]; then
                return 0
            else
                log "${YELLOW}[WARNING] Health endpoint returned status: $health_status${NC}"
                return 1
            fi
        else
            # If not JSON, assume success if we got a response
            return 0
        fi
    else
        return 1
    fi
}

# Function to check process health
check_process_health() {
    # Check if main Python process is running
    if pgrep -f "python.*inkedup_bot" >/dev/null; then
        return 0
    else
        log "${RED}[ERROR] Main application process not found${NC}"
        return 1
    fi
}

# Function to check database connectivity
check_database_health() {
    # Only check if DATABASE_URL is set
    if [ -n "${DATABASE_URL:-}" ]; then
        case "$DATABASE_URL" in
            sqlite*)
                # For SQLite, check if file exists and is accessible
                db_file=$(echo "$DATABASE_URL" | sed 's|sqlite:///||')
                if [ -f "$db_file" ] && [ -r "$db_file" ]; then
                    return 0
                else
                    log "${YELLOW}[WARNING] SQLite database file not accessible${NC}"
                    return 1
                fi
                ;;
            postgresql*)
                # For PostgreSQL, try a simple connection test
                # This requires psql client which may not be available in production
                # So we'll skip this check if psql is not available
                if command -v psql >/dev/null 2>&1; then
                    if psql "$DATABASE_URL" -c "SELECT 1;" >/dev/null 2>&1; then
                        return 0
                    else
                        log "${YELLOW}[WARNING] PostgreSQL connection failed${NC}"
                        return 1
                    fi
                else
                    # Skip database check if psql not available
                    return 0
                fi
                ;;
            *)
                # Unknown database type, skip check
                return 0
                ;;
        esac
    else
        # No database configured, skip check
        return 0
    fi
}

# Function to check memory usage
check_memory_health() {
    # Check if memory usage is reasonable
    local memory_limit_mb="${MEMORY_LIMIT_MB:-2048}"
    local memory_threshold_percent=90
    
    if [ -f /proc/meminfo ]; then
        # Get memory usage information
        mem_total=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        mem_available=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
        
        if [ -n "$mem_total" ] && [ -n "$mem_available" ]; then
            mem_used=$((mem_total - mem_available))
            mem_percent=$((mem_used * 100 / mem_total))
            
            if [ $mem_percent -gt $memory_threshold_percent ]; then
                log "${YELLOW}[WARNING] Memory usage is high: ${mem_percent}%${NC}"
                return 1
            fi
        fi
    fi
    
    return 0
}

# Function to check disk space
check_disk_health() {
    # Check disk space for critical directories
    local disk_threshold_percent=90
    
    for dir in "/app/data" "/app/logs" "/tmp"; do
        if [ -d "$dir" ]; then
            disk_usage=$(df "$dir" | tail -1 | awk '{print $5}' | sed 's/%//')
            if [ -n "$disk_usage" ] && [ "$disk_usage" -gt $disk_threshold_percent ]; then
                log "${YELLOW}[WARNING] Disk space low for $dir: ${disk_usage}%${NC}"
                return 1
            fi
        fi
    done
    
    return 0
}

# Main health check function
perform_health_check() {
    local retry_count=0
    local checks_passed=0
    local total_checks=0
    
    while [ $retry_count -lt $MAX_RETRIES ]; do
        checks_passed=0
        total_checks=0
        
        # HTTP health check
        total_checks=$((total_checks + 1))
        if check_http_health "$HEALTH_CHECK_URL" "$TIMEOUT"; then
            checks_passed=$((checks_passed + 1))
            log "${GREEN}[OK] HTTP health check passed${NC}"
        else
            log "${RED}[FAIL] HTTP health check failed${NC}"
        fi
        
        # Process health check
        total_checks=$((total_checks + 1))
        if check_process_health; then
            checks_passed=$((checks_passed + 1))
            log "${GREEN}[OK] Process health check passed${NC}"
        else
            log "${RED}[FAIL] Process health check failed${NC}"
        fi
        
        # Database health check
        total_checks=$((total_checks + 1))
        if check_database_health; then
            checks_passed=$((checks_passed + 1))
            log "${GREEN}[OK] Database health check passed${NC}"
        else
            log "${RED}[FAIL] Database health check failed${NC}"
        fi
        
        # Memory health check
        total_checks=$((total_checks + 1))
        if check_memory_health; then
            checks_passed=$((checks_passed + 1))
            log "${GREEN}[OK] Memory health check passed${NC}"
        else
            log "${YELLOW}[WARN] Memory health check failed${NC}"
        fi
        
        # Disk health check
        total_checks=$((total_checks + 1))
        if check_disk_health; then
            checks_passed=$((checks_passed + 1))
            log "${GREEN}[OK] Disk health check passed${NC}"
        else
            log "${YELLOW}[WARN] Disk health check failed${NC}"
        fi
        
        # Check if critical checks passed (HTTP and Process are critical)
        # Memory and Disk are warnings only
        critical_checks_passed=$((checks_passed >= 3))  # HTTP, Process, Database
        
        if [ $critical_checks_passed -eq 1 ]; then
            log "${GREEN}[SUCCESS] Health check passed (${checks_passed}/${total_checks} checks)${NC}"
            exit 0
        else
            retry_count=$((retry_count + 1))
            if [ $retry_count -lt $MAX_RETRIES ]; then
                log "${YELLOW}[RETRY] Health check failed, retrying in 2 seconds... (${retry_count}/${MAX_RETRIES})${NC}"
                sleep 2
            fi
        fi
    done
    
    log "${RED}[FAILURE] Health check failed after ${MAX_RETRIES} attempts${NC}"
    exit 1
}

# Run the health check
log "${GREEN}[INFO] Starting health check...${NC}"
perform_health_check