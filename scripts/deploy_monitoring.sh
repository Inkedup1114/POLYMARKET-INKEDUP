#!/bin/bash

# Deploy InkedUp Trading Bot Monitoring Stack
# This script sets up the complete monitoring infrastructure

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
COMPOSE_FILE="docker-compose.monitoring.yml"
PROJECT_NAME="inkedup-monitoring"
MONITORING_DIR="monitoring"

echo -e "${BLUE}🚀 InkedUp Trading Bot - Monitoring Stack Deployment${NC}"
echo "=================================================="

# Function to print colored output
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker."
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if monitoring configuration files exist
    if [ ! -f "$COMPOSE_FILE" ]; then
        log_error "Docker Compose file ($COMPOSE_FILE) not found."
        exit 1
    fi
    
    if [ ! -d "$MONITORING_DIR" ]; then
        log_error "Monitoring configuration directory ($MONITORING_DIR) not found."
        exit 1
    fi
    
    log_success "Prerequisites check completed"
}

# Create necessary directories and set permissions
setup_directories() {
    log_info "Setting up directories and permissions..."
    
    # Create log directories if they don't exist
    mkdir -p /var/log/inkedup/{trading,websocket,database,errors}
    
    # Set appropriate permissions
    chmod 755 /var/log/inkedup
    chmod 755 /var/log/inkedup/*
    
    # Create monitoring data directories
    mkdir -p ./monitoring/{prometheus,grafana,alertmanager,loki}/data
    
    # Set permissions for Grafana (runs as user 472)
    chmod 777 ./monitoring/grafana/data
    
    log_success "Directories and permissions configured"
}

# Deploy monitoring stack
deploy_stack() {
    log_info "Deploying monitoring stack..."
    
    # Pull latest images
    log_info "Pulling Docker images..."
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" pull
    
    # Start the monitoring stack
    log_info "Starting monitoring services..."
    docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d
    
    log_success "Monitoring stack deployed successfully"
}

# Wait for services to be ready
wait_for_services() {
    log_info "Waiting for services to be ready..."
    
    # Define services and their health check URLs
    declare -A services=(
        ["Prometheus"]="http://localhost:9090/-/ready"
        ["Grafana"]="http://localhost:3000/api/health"
        ["AlertManager"]="http://localhost:9093/-/ready"
        ["Loki"]="http://localhost:3100/ready"
    )
    
    for service in "${!services[@]}"; do
        url="${services[$service]}"
        log_info "Checking $service..."
        
        # Wait up to 60 seconds for service to be ready
        for i in {1..12}; do
            if curl -f -s "$url" > /dev/null 2>&1; then
                log_success "$service is ready"
                break
            fi
            
            if [ $i -eq 12 ]; then
                log_warning "$service is taking longer than expected to start"
            else
                sleep 5
            fi
        done
    done
}

# Configure Grafana datasources and dashboards
configure_grafana() {
    log_info "Configuring Grafana..."
    
    # Wait for Grafana to be fully ready
    sleep 10
    
    # Grafana should auto-provision datasources and dashboards
    # Check if they're configured correctly
    if curl -f -s -u admin:admin123 "http://localhost:3000/api/datasources" | grep -q "Prometheus"; then
        log_success "Grafana datasources configured"
    else
        log_warning "Grafana datasources might need manual configuration"
    fi
}

# Validate monitoring stack
validate_stack() {
    log_info "Validating monitoring stack..."
    
    # Check if all containers are running
    containers=("prometheus" "grafana" "alertmanager" "loki" "promtail" "node-exporter" "cadvisor")
    
    for container in "${containers[@]}"; do
        if docker ps | grep -q "inkedup_$container"; then
            log_success "$container is running"
        else
            log_error "$container is not running"
            return 1
        fi
    done
    
    # Check if metrics are being collected
    if curl -f -s "http://localhost:9090/api/v1/query?query=up" | grep -q "success"; then
        log_success "Prometheus is collecting metrics"
    else
        log_warning "Prometheus might not be collecting metrics properly"
    fi
    
    log_success "Monitoring stack validation completed"
}

# Display access information
show_access_info() {
    log_info "Monitoring Stack Access Information"
    echo "=================================="
    echo ""
    echo -e "${GREEN}🎯 Service URLs:${NC}"
    echo "  • Grafana Dashboard:    http://localhost:3000 (admin/admin123)"
    echo "  • Prometheus:           http://localhost:9090"
    echo "  • AlertManager:         http://localhost:9093"
    echo "  • Node Exporter:        http://localhost:9100"
    echo "  • cAdvisor:            http://localhost:8080"
    echo "  • Loki:                http://localhost:3100"
    echo ""
    echo -e "${YELLOW}📊 Key Features:${NC}"
    echo "  • Real-time system and application monitoring"
    echo "  • Trading-specific metrics and alerts"
    echo "  • Log aggregation and analysis"
    echo "  • Alert notifications and management"
    echo "  • Performance dashboards"
    echo ""
    echo -e "${BLUE}🔍 Quick Health Check:${NC}"
    echo "  • Check all services: docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps"
    echo "  • View logs:          docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f [service]"
    echo "  • Stop stack:         docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down"
    echo ""
}

# Main deployment function
main() {
    echo -e "${BLUE}Starting monitoring stack deployment...${NC}"
    echo ""
    
    check_prerequisites
    setup_directories
    deploy_stack
    wait_for_services
    configure_grafana
    validate_stack
    show_access_info
    
    log_success "🎉 Monitoring stack deployment completed successfully!"
    echo ""
    log_info "The InkedUp Trading Bot monitoring stack is now running."
    log_info "Visit http://localhost:3000 to access the Grafana dashboard."
}

# Handle script arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "stop")
        log_info "Stopping monitoring stack..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down
        log_success "Monitoring stack stopped"
        ;;
    "restart")
        log_info "Restarting monitoring stack..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" restart
        log_success "Monitoring stack restarted"
        ;;
    "status")
        log_info "Monitoring stack status:"
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" ps
        ;;
    "logs")
        service=${2:-}
        if [ -n "$service" ]; then
            docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs -f "$service"
        else
            docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" logs -f
        fi
        ;;
    "update")
        log_info "Updating monitoring stack..."
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" pull
        docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d
        log_success "Monitoring stack updated"
        ;;
    "clean")
        log_warning "This will remove all monitoring data. Are you sure? (y/N)"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            log_info "Cleaning monitoring stack..."
            docker-compose -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down -v
            docker system prune -f
            log_success "Monitoring stack cleaned"
        else
            log_info "Clean operation cancelled"
        fi
        ;;
    "help"|"-h"|"--help")
        echo "InkedUp Trading Bot - Monitoring Stack Deployment Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  deploy    Deploy the monitoring stack (default)"
        echo "  stop      Stop the monitoring stack"
        echo "  restart   Restart the monitoring stack"
        echo "  status    Show status of monitoring services"
        echo "  logs      Show logs (optional: specify service name)"
        echo "  update    Update and restart the monitoring stack"
        echo "  clean     Remove monitoring stack and data (destructive)"
        echo "  help      Show this help message"
        echo ""
        echo "Examples:"
        echo "  $0                    # Deploy monitoring stack"
        echo "  $0 logs prometheus    # Show Prometheus logs"
        echo "  $0 status            # Show service status"
        ;;
    *)
        log_error "Unknown command: $1"
        log_info "Run '$0 help' for usage information"
        exit 1
        ;;
esac