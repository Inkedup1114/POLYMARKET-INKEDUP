#!/bin/bash
set -euo pipefail

# Deployment script for InkedUp Polymarket Bot
# This script handles deployment to different environments (staging, production)

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEPLOY_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEPLOY_LOG="/tmp/inkedup_deploy_${DEPLOY_TIMESTAMP}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$DEPLOY_LOG"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$DEPLOY_LOG"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$DEPLOY_LOG"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$DEPLOY_LOG"
}

# Help function
show_help() {
    cat << EOF
InkedUp Polymarket Bot Deployment Script

Usage: $0 [OPTIONS] ENVIRONMENT

ENVIRONMENTS:
    staging     Deploy to staging environment
    production  Deploy to production environment
    local       Deploy to local development environment

OPTIONS:
    -h, --help              Show this help message
    -v, --version VERSION   Deploy specific version (default: latest)
    -f, --force             Force deployment without confirmation
    --skip-tests            Skip running tests before deployment
    --skip-backup           Skip database backup (not recommended)
    --rollback VERSION      Rollback to previous version
    --dry-run               Show what would be deployed without executing

EXAMPLES:
    $0 staging                    # Deploy latest to staging
    $0 production -v v1.2.3       # Deploy specific version to production
    $0 production --rollback v1.2.2  # Rollback to previous version
    $0 staging --dry-run          # Show deployment plan

EOF
}

# Parse command line arguments
ENVIRONMENT=""
VERSION="latest"
FORCE=false
SKIP_TESTS=false
SKIP_BACKUP=false
ROLLBACK=""
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --rollback)
            ROLLBACK="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        staging|production|local)
            ENVIRONMENT="$1"
            shift
            ;;
        *)
            error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validate arguments
if [[ -z "$ENVIRONMENT" ]]; then
    error "Environment is required"
    show_help
    exit 1
fi

if [[ "$ENVIRONMENT" != "staging" && "$ENVIRONMENT" != "production" && "$ENVIRONMENT" != "local" ]]; then
    error "Invalid environment: $ENVIRONMENT"
    exit 1
fi

# Load environment specific configuration
ENV_CONFIG="${SCRIPT_DIR}/env/${ENVIRONMENT}.env"
if [[ -f "$ENV_CONFIG" ]]; then
    source "$ENV_CONFIG"
    log "Loaded configuration for $ENVIRONMENT"
else
    warning "No environment config found at $ENV_CONFIG"
fi

# Pre-deployment checks
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check required tools
    local required_tools=("docker" "docker-compose" "git" "curl")
    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            error "Required tool not found: $tool"
            exit 1
        fi
    done
    
    # Check Docker is running
    if ! docker info &> /dev/null; then
        error "Docker is not running"
        exit 1
    fi
    
    # Check git status
    cd "$PROJECT_ROOT"
    if [[ -n "$(git status --porcelain)" ]]; then
        warning "Working directory has uncommitted changes"
        if [[ "$FORCE" != true ]]; then
            error "Use --force to deploy with uncommitted changes"
            exit 1
        fi
    fi
    
    success "Prerequisites check passed"
}

# Run tests before deployment
run_tests() {
    if [[ "$SKIP_TESTS" == true ]]; then
        warning "Skipping tests as requested"
        return
    fi
    
    log "Running test suite..."
    cd "$PROJECT_ROOT"
    
    # Run different test suites based on environment
    case $ENVIRONMENT in
        production)
            # Full test suite for production
            python -m pytest tests/ -v --cov=inkedup_bot --cov-fail-under=80 -m "not slow"
            ;;
        staging)
            # Quick test suite for staging
            python -m pytest tests/ -v -m "unit and not slow"
            ;;
        local)
            # Minimal tests for local
            python -m pytest tests/ -v -m "smoke"
            ;;
    esac
    
    if [[ $? -ne 0 ]]; then
        error "Tests failed, aborting deployment"
        exit 1
    fi
    
    success "All tests passed"
}

# Create database backup
backup_database() {
    if [[ "$SKIP_BACKUP" == true ]]; then
        warning "Skipping database backup as requested"
        return
    fi
    
    if [[ -z "${DATABASE_URL:-}" ]]; then
        warning "No DATABASE_URL configured, skipping backup"
        return
    fi
    
    log "Creating database backup..."
    
    local backup_file="/tmp/db_backup_${ENVIRONMENT}_${DEPLOY_TIMESTAMP}.sql"
    
    # Create backup based on database type
    if [[ "$DATABASE_URL" == sqlite* ]]; then
        local db_file=$(echo "$DATABASE_URL" | sed 's/sqlite:\/\/\///')
        if [[ -f "$db_file" ]]; then
            cp "$db_file" "${backup_file%.sql}.db"
            success "SQLite database backed up to ${backup_file%.sql}.db"
        fi
    elif [[ "$DATABASE_URL" == postgresql* ]]; then
        pg_dump "$DATABASE_URL" > "$backup_file"
        success "PostgreSQL database backed up to $backup_file"
    else
        warning "Unknown database type, skipping backup"
    fi
}

# Build application
build_application() {
    log "Building application..."
    cd "$PROJECT_ROOT"
    
    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would build Docker image with tag: $VERSION"
        return
    fi
    
    # Build Docker image
    docker build \
        -t "inkedup-polymarket-bot:${VERSION}" \
        -t "inkedup-polymarket-bot:latest" \
        --build-arg BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        --build-arg VERSION="$VERSION" \
        --build-arg VCS_REF="$(git rev-parse HEAD)" \
        .
    
    if [[ $? -ne 0 ]]; then
        error "Build failed"
        exit 1
    fi
    
    success "Application built successfully"
}

# Deploy application
deploy_application() {
    log "Deploying to $ENVIRONMENT..."
    
    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would deploy the following:"
        log "  Environment: $ENVIRONMENT"
        log "  Version: $VERSION"
        log "  Image: inkedup-polymarket-bot:$VERSION"
        return
    fi
    
    # Environment specific deployment
    case $ENVIRONMENT in
        production)
            deploy_production
            ;;
        staging)
            deploy_staging
            ;;
        local)
            deploy_local
            ;;
    esac
}

# Production deployment
deploy_production() {
    log "Deploying to production environment..."
    
    # Use production docker-compose file
    export COMPOSE_FILE="docker-compose.prod.yml"
    export IMAGE_TAG="$VERSION"
    
    # Stop existing services gracefully
    docker-compose down --timeout 30
    
    # Pull latest images
    docker-compose pull
    
    # Start services
    docker-compose up -d
    
    # Wait for services to be healthy
    wait_for_health_check
    
    success "Production deployment completed"
}

# Staging deployment
deploy_staging() {
    log "Deploying to staging environment..."
    
    export COMPOSE_FILE="docker-compose.staging.yml"
    export IMAGE_TAG="$VERSION"
    
    docker-compose down
    docker-compose up -d
    
    wait_for_health_check
    
    success "Staging deployment completed"
}

# Local deployment
deploy_local() {
    log "Deploying to local environment..."
    
    export COMPOSE_FILE="docker-compose.yml"
    export IMAGE_TAG="$VERSION"
    
    docker-compose down
    docker-compose up -d
    
    success "Local deployment completed"
}

# Health check
wait_for_health_check() {
    log "Waiting for application to be healthy..."
    
    local health_url="${HEALTH_CHECK_URL:-http://localhost:8080/health}"
    local max_attempts=30
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        if curl -f -s "$health_url" > /dev/null; then
            success "Application is healthy"
            return 0
        fi
        
        attempt=$((attempt + 1))
        log "Health check attempt $attempt/$max_attempts..."
        sleep 10
    done
    
    error "Application failed to become healthy"
    return 1
}

# Rollback functionality
rollback_deployment() {
    if [[ -z "$ROLLBACK" ]]; then
        return
    fi
    
    log "Rolling back to version $ROLLBACK..."
    
    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would rollback to version: $ROLLBACK"
        return
    fi
    
    # Deploy the rollback version
    VERSION="$ROLLBACK"
    deploy_application
    
    success "Rollback to $ROLLBACK completed"
}

# Post-deployment tasks
post_deployment() {
    log "Running post-deployment tasks..."
    
    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would run post-deployment tasks"
        return
    fi
    
    # Run database migrations
    if [[ -n "${DATABASE_URL:-}" ]]; then
        log "Running database migrations..."
        docker-compose exec -T app alembic upgrade head
    fi
    
    # Clear caches
    log "Clearing application caches..."
    # Add cache clearing logic here
    
    # Notify monitoring systems
    if [[ -n "${MONITORING_WEBHOOK:-}" ]]; then
        log "Notifying monitoring systems..."
        curl -X POST "$MONITORING_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"event\":\"deployment\",\"environment\":\"$ENVIRONMENT\",\"version\":\"$VERSION\",\"timestamp\":\"$(date -Iseconds)\"}"
    fi
    
    success "Post-deployment tasks completed"
}

# Cleanup
cleanup() {
    log "Cleaning up..."
    
    # Remove old Docker images
    docker image prune -f
    
    # Clean up old log files (keep last 5)
    find /tmp -name "inkedup_deploy_*.log" -type f | sort | head -n -5 | xargs rm -f
    
    success "Cleanup completed"
}

# Main deployment flow
main() {
    log "Starting deployment of InkedUp Polymarket Bot"
    log "Environment: $ENVIRONMENT"
    log "Version: $VERSION"
    log "Timestamp: $DEPLOY_TIMESTAMP"
    
    # Confirmation for production deployments
    if [[ "$ENVIRONMENT" == "production" && "$FORCE" != true && "$DRY_RUN" != true ]]; then
        echo -n "Are you sure you want to deploy to PRODUCTION? (yes/no): "
        read -r confirmation
        if [[ "$confirmation" != "yes" ]]; then
            log "Deployment cancelled by user"
            exit 0
        fi
    fi
    
    # Handle rollback
    if [[ -n "$ROLLBACK" ]]; then
        rollback_deployment
        exit 0
    fi
    
    # Execute deployment steps
    check_prerequisites
    run_tests
    backup_database
    build_application
    deploy_application
    post_deployment
    cleanup
    
    success "Deployment completed successfully!"
    log "Deployment log saved to: $DEPLOY_LOG"
    
    # Print deployment summary
    cat << EOF

====================================
    DEPLOYMENT SUMMARY
====================================
Environment: $ENVIRONMENT
Version: $VERSION
Timestamp: $DEPLOY_TIMESTAMP
Log File: $DEPLOY_LOG
====================================

EOF
}

# Error handling
trap 'error "Deployment failed at line $LINENO"' ERR

# Run main function
main "$@"