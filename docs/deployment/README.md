# InkedUp Polymarket Bot - Deployment Guide

This guide provides comprehensive instructions for deploying the InkedUp Polymarket Bot across different environments.

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Deployment Methods](#deployment-methods)
5. [Configuration Management](#configuration-management)
6. [Monitoring and Health Checks](#monitoring-and-health-checks)
7. [Security Considerations](#security-considerations)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance](#maintenance)

## Overview

The InkedUp Polymarket Bot supports deployment across multiple environments:

- **Local Development**: Single-container setup for development and testing
- **Staging**: Multi-container setup with basic monitoring for integration testing
- **Production**: High-availability setup with full monitoring, security, and backup

### Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │────│   Application   │────│    Database     │
│     (NGINX)     │    │   (Bot + API)   │    │  (PostgreSQL)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐             │
         │              │      Redis      │             │
         │              │     (Cache)     │             │
         │              └─────────────────┘             │
         │                       │                       │
┌─────────────────────────────────────────────────────────────────┐
│                    Monitoring Stack                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ Prometheus  │ │   Grafana   │ │ Alertmanager│               │
│  └─────────────┘ └─────────────┘ └─────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Prerequisites

### System Requirements

**Minimum Requirements:**
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB SSD
- Network: Stable internet connection

**Recommended Requirements:**
- CPU: 4+ cores
- RAM: 8GB+
- Storage: 50GB+ SSD
- Network: Low-latency connection

### Required Software

1. **Docker** (20.10+)
2. **Docker Compose** (2.0+)
3. **Git** (2.30+)
4. **OpenSSL** (for generating secrets)

### Installation

#### Ubuntu/Debian
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin

# Install additional tools
sudo apt install git openssl curl jq
```

#### CentOS/RHEL
```bash
# Update system
sudo yum update -y

# Install Docker
sudo yum install -y yum-utils
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo yum install -y docker-ce docker-ce-cli containerd.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Install additional tools
sudo yum install -y git openssl curl jq
```

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/inkedup/polymarket-bot.git
cd polymarket-bot
```

### 2. Environment Configuration

Copy the environment template and configure for your target environment:

```bash
# For local development
cp .env.example .env

# For staging/production, use environment-specific configs
cp scripts/deployment/env/staging.env .env.staging
cp scripts/deployment/env/production.env .env.production
```

### 3. Generate Secrets

```bash
# Generate JWT secret
export JWT_SECRET_KEY=$(openssl rand -base64 32)

# Generate database password
export DB_PASSWORD=$(openssl rand -base64 24)

# Generate Redis password (for production)
export REDIS_PASSWORD=$(openssl rand -base64 24)
```

### 4. Configure Trading Credentials

⚠️ **SECURITY WARNING**: Never commit real private keys to version control!

```bash
# Set your Ethereum private key
export PRIVATE_KEY="your_ethereum_private_key"
export PUBLIC_KEY="your_ethereum_public_address"
```

## Deployment Methods

### Local Development

Quick start for development:

```bash
# Build and start services
docker-compose up -d

# View logs
docker-compose logs -f app

# Access services
# Application: http://localhost:8080
# Grafana: http://localhost:3000 (admin/admin)
# Prometheus: http://localhost:9090
```

### Staging Environment

Deploy to staging for integration testing:

```bash
# Set environment variables
export IMAGE_TAG=staging-$(date +%Y%m%d-%H%M%S)
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export VCS_REF=$(git rev-parse HEAD)

# Run deployment script
./scripts/deployment/deploy.sh staging --version $IMAGE_TAG

# Or manual deployment
docker-compose -f docker-compose.staging.yml up -d
```

### Production Environment

Automated production deployment:

```bash
# Run full deployment with safety checks
./scripts/deployment/deploy.sh production --version v1.0.0

# With custom options
./scripts/deployment/deploy.sh production \
  --version v1.0.0 \
  --skip-tests \
  --force
```

#### Manual Production Deployment

```bash
# Set production environment variables
export IMAGE_TAG=v1.0.0
export BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export VCS_REF=$(git rev-parse HEAD)
export COMPOSE_PROJECT_NAME=inkedup-production

# Deploy
docker-compose -f docker-compose.prod.yml up -d

# Verify deployment
docker-compose -f docker-compose.prod.yml ps
curl http://localhost:8080/health
```

### Rolling Updates

For zero-downtime updates in production:

```bash
# Scale up with new version
docker-compose -f docker-compose.prod.yml up -d --scale app=3

# Health check new instances
for i in {1..3}; do
  docker-compose -f docker-compose.prod.yml exec app-replica-$i curl http://localhost:8080/health
done

# Traffic will automatically route to healthy instances
```

## Configuration Management

### Environment Variables

Key configuration categories:

#### Trading Configuration
```bash
PRIVATE_KEY=your_ethereum_private_key
PUBLIC_KEY=your_ethereum_public_address
POLYMARKET_API_BASE=https://clob.polymarket.com
```

#### Risk Management
```bash
GLOBAL_RISK_CAP=10000.0
MAX_POSITION_SIZE=1000.0
MAX_MARKET_EXPOSURE=2500.0
```

#### Performance Tuning
```bash
MARKET_CACHE_TTL=300
BOOK_CACHE_TTL=30
MAX_CONCURRENT_REQUESTS=20
```

### Docker Compose Override

Create environment-specific overrides:

```yaml
# docker-compose.override.yml
version: '3.8'
services:
  app:
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
    volumes:
      - ./logs:/app/logs
```

### Secrets Management

#### Docker Secrets (Recommended)
```bash
# Create secrets
echo "your_private_key" | docker secret create private_key -
echo "your_jwt_secret" | docker secret create jwt_secret -

# Reference in docker-compose.yml
services:
  app:
    secrets:
      - private_key
      - jwt_secret
```

#### External Secrets Manager
For production, consider using:
- AWS Secrets Manager
- Azure Key Vault  
- HashiCorp Vault
- Kubernetes Secrets

## Monitoring and Health Checks

### Built-in Health Checks

The application provides several health check endpoints:

```bash
# Basic health check
curl http://localhost:8080/health

# Readiness check (Kubernetes-style)
curl http://localhost:8080/readiness

# Prometheus metrics
curl http://localhost:8080/metrics
```

### Health Check Response Format

```json
{
  "status": "healthy",
  "timestamp": "2024-01-20T10:30:00Z",
  "checks": {
    "database_connection": {
      "status": "healthy",
      "message": "Database connection successful"
    },
    "system_memory": {
      "status": "healthy", 
      "usage_percent": 45.2
    }
  },
  "summary": {
    "total_checks": 4,
    "healthy": 4,
    "degraded": 0,
    "unhealthy": 0
  }
}
```

### Monitoring Stack

#### Prometheus Configuration

Metrics are automatically collected from:
- Application metrics (`/metrics`)
- System metrics (Node Exporter)
- Container metrics (cAdvisor)

#### Grafana Dashboards

Pre-configured dashboards:
- **Trading Overview**: Orders, positions, P&L
- **System Health**: CPU, memory, disk usage  
- **Performance**: Response times, throughput
- **Business Intelligence**: Strategy performance

Access Grafana at `http://localhost:3000` (admin/admin)

#### Alerting

Key alerts configured:
- **Critical**: System down, high error rate, risk cap exceeded
- **Warning**: High resource usage, slow performance
- **Business**: Low trading volume, strategy underperformance

### Log Management

#### Log Configuration
```bash
# Environment variables
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/app/logs/app.log
ENABLE_AUDIT_LOGS=true
```

#### Centralized Logging
For production, consider:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Fluentd + OpenSearch
- Grafana Loki

## Security Considerations

### Container Security

#### Non-root User
All containers run as non-root user:
```dockerfile
RUN groupadd -r inkedup && useradd --no-log-init -r -g inkedup inkedup
USER inkedup
```

#### Security Scanning
Automated security scans with:
- Trivy (vulnerability scanning)
- Docker Scout (security analysis)
- Hadolint (Dockerfile linting)

#### Network Security
```yaml
# Production network isolation
networks:
  inkedup-prod:
    driver: bridge
    driver_opts:
      com.docker.network.bridge.name: br-inkedup-prod
    ipam:
      config:
        - subnet: 172.30.0.0/16
```

### Secrets Management

#### Environment Variables
```bash
# Use environment variables for secrets
export PRIVATE_KEY="$(cat /secure/path/to/private.key)"
export JWT_SECRET_KEY="$(openssl rand -base64 32)"
```

#### File-based Secrets
```bash
# Mount secrets as files
volumes:
  - /secure/secrets:/run/secrets:ro
```

### TLS/SSL Configuration

#### NGINX SSL Termination
```nginx
server {
    listen 443 ssl http2;
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
}
```

## Troubleshooting

### Common Issues

#### 1. Container Won't Start
```bash
# Check logs
docker-compose logs app

# Check resource usage
docker stats

# Verify configuration
docker-compose config
```

#### 2. Database Connection Failed
```bash
# Check database status
docker-compose exec database psql -U prod_user -d inkedup_production -c "SELECT 1"

# Check network connectivity
docker-compose exec app ping database

# Verify credentials
docker-compose exec app env | grep DATABASE
```

#### 3. High Memory Usage
```bash
# Check memory usage
docker stats --no-stream

# Adjust container limits
docker-compose up -d --scale app=2

# Monitor application metrics
curl http://localhost:8080/metrics | grep memory
```

#### 4. API Rate Limiting
```bash
# Check rate limit status
curl -I http://localhost:8080/api/markets

# Adjust rate limits
export RATE_LIMIT_PER_MINUTE=1000
docker-compose restart app
```

### Diagnostic Commands

```bash
# Container status
docker-compose ps

# Resource usage
docker system df
docker system prune -f

# Network connectivity
docker network ls
docker network inspect inkedup-prod

# Service discovery
docker-compose exec app nslookup database
```

### Log Analysis

```bash
# Application logs
docker-compose logs -f app

# Database logs  
docker-compose logs -f database

# Search for errors
docker-compose logs app | grep ERROR

# Monitor real-time
tail -f logs/app.log | jq .
```

## Maintenance

### Regular Updates

#### Dependency Updates
```bash
# Update base images
docker-compose pull

# Rebuild with latest dependencies
docker-compose build --no-cache

# Update Python dependencies
poetry update
docker-compose build app
```

#### Security Updates
```bash
# Run security scan
./scripts/security/scan.sh

# Update base images
docker-compose build --no-cache --pull
```

### Backup and Recovery

#### Database Backup
```bash
# Manual backup
docker-compose exec database pg_dump -U prod_user inkedup_production > backup.sql

# Automated backup (using deployment script)
./scripts/deployment/deploy.sh production --backup-only
```

#### Application State Backup
```bash
# Backup application data
docker-compose exec app tar -czf /tmp/app-data.tar.gz /app/data

# Copy from container
docker cp $(docker-compose ps -q app):/tmp/app-data.tar.gz ./app-data-$(date +%Y%m%d).tar.gz
```

#### Recovery Procedure
```bash
# Stop services
docker-compose down

# Restore database
docker-compose exec database psql -U prod_user -d inkedup_production < backup.sql

# Restore application data
docker cp ./app-data-backup.tar.gz $(docker-compose ps -q app):/tmp/
docker-compose exec app tar -xzf /tmp/app-data-backup.tar.gz -C /

# Restart services
docker-compose up -d
```

### Performance Optimization

#### Resource Tuning
```yaml
# docker-compose.prod.yml
services:
  app:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
```

#### Database Optimization
```sql
-- Performance tuning queries
EXPLAIN ANALYZE SELECT * FROM orders WHERE status = 'active';
VACUUM ANALYZE;
REINDEX INDEX idx_orders_status;
```

### Scaling

#### Horizontal Scaling
```bash
# Scale application instances
docker-compose up -d --scale app=3

# Verify load balancing
for i in {1..10}; do curl http://localhost:8080/ping; done
```

#### Vertical Scaling
```yaml
# Increase resource limits
services:
  app:
    deploy:
      resources:
        limits:
          memory: 4G
          cpus: '2.0'
```

---

## Quick Reference

### Essential Commands

```bash
# Deploy to staging
./scripts/deployment/deploy.sh staging

# Deploy to production
./scripts/deployment/deploy.sh production --version v1.0.0

# Health check
curl http://localhost:8080/health

# View logs
docker-compose logs -f app

# Scale services
docker-compose up -d --scale app=3

# Backup database
./scripts/deployment/deploy.sh production --backup-only

# Security scan
./scripts/security/scan.sh
```

### Support

- **Documentation**: [docs/](../README.md)
- **Issues**: [GitHub Issues](https://github.com/inkedup/polymarket-bot/issues)
- **Security**: [SECURITY.md](../../SECURITY.md)

---

**Last Updated**: January 20, 2024  
**Version**: 1.0.0