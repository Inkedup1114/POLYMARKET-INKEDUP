# CI/CD Pipeline Documentation

This document provides comprehensive documentation for the Continuous Integration and Continuous Deployment (CI/CD) pipeline implemented for the InkedUp Polymarket Bot.

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [Workflow Structure](#workflow-structure)
3. [Testing Strategy](#testing-strategy)
4. [Security Integration](#security-integration)
5. [Deployment Automation](#deployment-automation)
6. [Environment Management](#environment-management)
7. [Monitoring and Observability](#monitoring-and-observability)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

## Pipeline Overview

The CI/CD pipeline is designed to provide comprehensive automation for:
- **Code Quality**: Automated testing, linting, and code analysis
- **Security**: Vulnerability scanning and security policy enforcement
- **Build & Package**: Docker image creation and registry management
- **Deployment**: Automated deployment to staging and production
- **Monitoring**: Performance tracking and health verification

### Architecture

```mermaid
graph LR
    subgraph "Development"
        DEV[Developer Push]
        PR[Pull Request]
    end
    
    subgraph "CI Pipeline"
        TEST[Testing]
        SEC[Security Scan]
        BUILD[Build & Package]
        QUAL[Quality Gates]
    end
    
    subgraph "CD Pipeline"
        STAGE[Deploy Staging]
        VERIFY[Verification Tests]
        PROD[Deploy Production]
        MONITOR[Monitor & Alert]
    end
    
    DEV --> TEST
    PR --> TEST
    TEST --> SEC
    SEC --> BUILD
    BUILD --> QUAL
    QUAL --> STAGE
    STAGE --> VERIFY
    VERIFY --> PROD
    PROD --> MONITOR
```

## Workflow Structure

### 1. Main CI/CD Workflow (`.github/workflows/ci-cd.yml`)

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main`
- Manual workflow dispatch

**Jobs**:
1. **Test**: Multi-environment testing with coverage
2. **Security**: Vulnerability scanning and SAST
3. **Build**: Docker image creation and optimization
4. **Deploy**: Environment-specific deployments

```yaml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    strategy:
      matrix:
        python-version: [3.11, 3.12]
        os: [ubuntu-latest]
    # ... test implementation
  
  security:
    needs: test
    # ... security scanning
  
  build:
    needs: [test, security]
    # ... build and package
  
  deploy-staging:
    needs: build
    if: github.ref == 'refs/heads/develop'
    # ... staging deployment
  
  deploy-production:
    needs: build
    if: github.ref == 'refs/heads/main'
    # ... production deployment
```

### 2. Testing Workflow (`.github/workflows/test.yml`)

**Purpose**: Dedicated comprehensive testing pipeline

**Test Categories**:
- Unit tests with pytest
- Integration tests with database
- Performance benchmarks
- Load testing with Locust
- Mutation testing for code quality

### 3. Security Workflow (`.github/workflows/security.yml`)

**Purpose**: Comprehensive security analysis

**Security Checks**:
- Dependency vulnerability scanning (Safety, pip-audit)
- Static code analysis (Bandit, Semgrep, CodeQL)
- Secret scanning (TruffleHog, GitLeaks)
- Docker security scanning (Trivy, Scout)
- Infrastructure security (Checkov, Kics)

## Testing Strategy

### Test Pyramid

```
    ┌─────────────┐
    │   E2E       │ ← Integration & System Tests
    │   Tests     │
    ├─────────────┤
    │ Integration │ ← API & Database Tests  
    │   Tests     │
    ├─────────────┤
    │    Unit     │ ← Component & Unit Tests
    │   Tests     │
    └─────────────┘
```

### Test Configuration

#### Unit Tests
```yaml
- name: Run unit tests
  run: |
    poetry run pytest tests/ \
      -v \
      --cov=inkedup_bot \
      --cov-report=xml \
      --cov-report=html \
      -m "unit"
```

#### Integration Tests
```yaml
- name: Run integration tests
  run: |
    poetry run pytest tests/ \
      -v \
      --cov=inkedup_bot \
      --cov-append \
      -m "integration"
  env:
    DATABASE_URL: postgresql://test_user:test_pass@localhost/test_db
```

#### Performance Tests
```yaml
- name: Run performance tests
  run: |
    poetry run pytest tests/ \
      -v \
      --benchmark-only \
      --benchmark-json=benchmark.json \
      -m "performance"
```

#### Load Tests
```yaml
- name: Run load tests
  run: |
    poetry run locust \
      --headless \
      --users 50 \
      --spawn-rate 5 \
      --run-time 60s \
      --host http://localhost:8080 \
      -f tests/load_test.py
```

### Quality Gates

#### Coverage Requirements
```yaml
- name: Check coverage
  run: |
    poetry run coverage report --fail-under=80
    poetry run coverage xml
```

#### Code Quality
```yaml
- name: Run linting
  run: |
    poetry run ruff check inkedup_bot/
    poetry run black --check inkedup_bot/
    poetry run mypy inkedup_bot/
```

## Security Integration

### Multi-Layer Security Scanning

#### 1. Dependency Scanning
```yaml
- name: Run Safety check
  run: |
    poetry run safety check --json --output safety-report.json

- name: Run pip-audit
  run: |
    pip install pip-audit
    pip-audit --format=json --output=pip-audit-report.json
```

#### 2. Static Application Security Testing (SAST)
```yaml
- name: Run Bandit security scan
  run: |
    poetry run bandit -r inkedup_bot/ -f json -o bandit-report.json

- name: Run Semgrep
  uses: semgrep/semgrep-action@v1
  with:
    config: >-
      p/security-audit
      p/python
      p/bandit
      p/owasp-top-ten
```

#### 3. Secret Scanning
```yaml
- name: Run TruffleHog OSS
  uses: trufflesecurity/trufflehog@main
  with:
    path: ./
    base: main
    head: HEAD

- name: Run GitLeaks
  uses: gitleaks/gitleaks-action@v2
```

#### 4. Container Security
```yaml
- name: Run Trivy vulnerability scanner
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: 'inkedup-bot:latest'
    format: 'sarif'
    output: 'trivy-results.sarif'
```

### Security Policies

#### Branch Protection
```yaml
# Required status checks
required_status_checks:
  strict: true
  contexts:
    - "test"
    - "security"
    - "build"

# Required reviews
required_pull_request_reviews:
  required_approving_review_count: 2
  dismiss_stale_reviews: true
  require_code_owner_reviews: true

# Restrictions
restrictions:
  users: []
  teams: ["core-team"]
```

#### Security Baseline
```json
{
  "version": "1.4.0",
  "plugins_used": [
    {"name": "AWSKeyDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "PrivateKeyDetector"}
  ],
  "filters_used": [
    {"path": "detect_secrets.filters.allowlist.is_line_allowlisted"}
  ]
}
```

## Deployment Automation

### Environment Strategy

#### Deployment Flow
```mermaid
graph LR
    DEV[Development] --> STAGE[Staging]
    STAGE --> PROD[Production]
    
    subgraph "Staging"
        STAGE_TEST[Integration Tests]
        STAGE_VERIFY[Health Checks]
    end
    
    subgraph "Production"
        PROD_DEPLOY[Blue-Green Deploy]
        PROD_VERIFY[Smoke Tests]
        PROD_MONITOR[Monitoring]
    end
```

### Staging Deployment
```yaml
deploy-staging:
  runs-on: ubuntu-latest
  needs: [test, security, build]
  if: github.ref == 'refs/heads/develop'
  
  steps:
    - name: Deploy to staging
      run: |
        echo "${{ secrets.STAGING_SSH_KEY }}" > staging_key
        chmod 600 staging_key
        
        scp -i staging_key docker-compose.staging.yml staging-server:~/
        
        ssh -i staging_key staging-server << 'EOF'
          export IMAGE_TAG=${{ github.sha }}
          docker-compose -f docker-compose.staging.yml pull
          docker-compose -f docker-compose.staging.yml up -d
        EOF
    
    - name: Verify staging deployment
      run: |
        sleep 30
        curl -f http://staging.inkedup.com/health
```

### Production Deployment
```yaml
deploy-production:
  runs-on: ubuntu-latest
  needs: [test, security, build, deploy-staging]
  if: github.ref == 'refs/heads/main'
  environment: production
  
  steps:
    - name: Deployment approval
      uses: trstringer/manual-approval@v1
      with:
        secret: ${{ github.TOKEN }}
        approvers: core-team
        minimum-approvals: 2
    
    - name: Blue-green deployment
      run: |
        # Deploy to blue environment
        ./scripts/deployment/deploy.sh production --version ${{ github.sha }}
        
        # Run smoke tests
        ./scripts/testing/smoke-tests.sh production
        
        # Switch traffic if healthy
        ./scripts/deployment/switch-traffic.sh blue
    
    - name: Rollback on failure
      if: failure()
      run: |
        ./scripts/deployment/rollback.sh production
```

### Deployment Script Integration

The pipeline integrates with the deployment script:

```yaml
- name: Deploy with automation script
  run: |
    export IMAGE_TAG="${{ github.sha }}"
    export BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    export VCS_REF="${{ github.sha }}"
    
    ./scripts/deployment/deploy.sh production \
      --version ${{ github.sha }} \
      --skip-tests \
      --force
```

## Environment Management

### Environment Configuration

#### Development
```yaml
environment:
  name: development
  url: http://localhost:8080
variables:
  - DATABASE_URL: sqlite:///dev.db
  - DEBUG: true
  - LOG_LEVEL: DEBUG
```

#### Staging
```yaml
environment:
  name: staging
  url: https://staging.inkedup.com
secrets:
  - DATABASE_URL
  - PRIVATE_KEY
  - JWT_SECRET
variables:
  - APP_ENV: staging
  - DEBUG: false
```

#### Production
```yaml
environment:
  name: production
  url: https://app.inkedup.com
protection_rules:
  - required_reviewers: 2
  - wait_timer: 5
secrets:
  - DATABASE_URL
  - PRIVATE_KEY
  - JWT_SECRET
  - MONITORING_WEBHOOK
```

### Secrets Management

#### GitHub Secrets
```bash
# Repository secrets
DOCKER_REGISTRY_TOKEN
STAGING_SSH_KEY
PRODUCTION_SSH_KEY
DATABASE_PASSWORD
JWT_SECRET_KEY

# Environment secrets
STAGING_DATABASE_URL
PRODUCTION_DATABASE_URL
STAGING_PRIVATE_KEY
PRODUCTION_PRIVATE_KEY
```

#### External Secrets (Recommended)
```yaml
# HashiCorp Vault integration
- name: Get secrets from Vault
  uses: hashicorp/vault-action@v2
  with:
    url: https://vault.company.com
    token: ${{ secrets.VAULT_TOKEN }}
    secrets: |
      secret/data/staging database_url | DATABASE_URL
      secret/data/staging jwt_secret | JWT_SECRET
```

## Monitoring and Observability

### Pipeline Monitoring

#### Workflow Metrics
```yaml
- name: Report deployment metrics
  run: |
    curl -X POST "${{ secrets.MONITORING_WEBHOOK }}" \
      -H "Content-Type: application/json" \
      -d '{
        "event": "deployment",
        "environment": "production",
        "version": "${{ github.sha }}",
        "timestamp": "'$(date -Iseconds)'",
        "duration": "${{ job.duration }}",
        "status": "success"
      }'
```

#### Performance Tracking
```yaml
- name: Benchmark tracking
  run: |
    poetry run pytest tests/ --benchmark-json=benchmark.json
    
    # Upload to performance tracking system
    curl -X POST "https://perf-tracker.company.com/api/benchmarks" \
      -H "Content-Type: application/json" \
      -d @benchmark.json
```

### Deployment Health Checks

#### Post-deployment Verification
```yaml
- name: Health check verification
  run: |
    # Wait for application to start
    sleep 30
    
    # Check health endpoint
    response=$(curl -s -o /dev/null -w "%{http_code}" http://app.inkedup.com/health)
    if [ $response -ne 200 ]; then
      echo "Health check failed with status $response"
      exit 1
    fi
    
    # Check metrics endpoint
    curl -f http://app.inkedup.com/metrics > /dev/null
```

#### Smoke Tests
```yaml
- name: Run smoke tests
  run: |
    # Test critical functionality
    ./scripts/testing/smoke-tests.sh production
    
    # Verify trading functionality
    python -c "
    import requests
    response = requests.get('http://app.inkedup.com/api/markets')
    assert response.status_code == 200
    assert len(response.json()) > 0
    "
```

## Best Practices

### Pipeline Design

#### 1. Fail Fast Principle
```yaml
# Run fastest tests first
jobs:
  lint:
    # Quick syntax and style checks
  unit-test:
    # Fast unit tests
  integration-test:
    needs: [lint, unit-test]
    # Slower integration tests
  security:
    needs: [lint, unit-test]
    # Parallel security scanning
```

#### 2. Parallel Execution
```yaml
# Run independent jobs in parallel
jobs:
  test:
    strategy:
      matrix:
        python-version: [3.11, 3.12]
        test-type: [unit, integration]
      fail-fast: false
```

#### 3. Caching Strategy
```yaml
- name: Cache dependencies
  uses: actions/cache@v3
  with:
    path: ~/.cache/pip
    key: ${{ runner.os }}-pip-${{ hashFiles('**/poetry.lock') }}
    restore-keys: |
      ${{ runner.os }}-pip-
```

### Security Best Practices

#### 1. Least Privilege Access
```yaml
permissions:
  contents: read
  security-events: write
  packages: write
```

#### 2. Secret Rotation
```bash
# Automated secret rotation
#!/bin/bash
new_secret=$(openssl rand -base64 32)
gh secret set JWT_SECRET_KEY --body "$new_secret"
```

#### 3. Vulnerability Management
```yaml
- name: Security reporting
  if: always()
  run: |
    # Aggregate security reports
    python scripts/security/aggregate-reports.py
    
    # Send to security dashboard
    curl -X POST "$SECURITY_WEBHOOK" \
      -d @security-summary.json
```

### Quality Assurance

#### 1. Code Coverage
```yaml
- name: Coverage reporting
  run: |
    poetry run coverage combine
    poetry run coverage report --fail-under=80
    poetry run coverage html
```

#### 2. Performance Monitoring
```yaml
- name: Performance regression detection
  run: |
    # Compare with baseline
    python scripts/performance/regression-check.py \
      --baseline performance-baseline.json \
      --current benchmark.json \
      --threshold 10
```

## Troubleshooting

### Common Issues

#### 1. Test Failures
```bash
# Debug test failures
poetry run pytest -vvv --tb=long --capture=no tests/test_failing.py

# Run specific test with debugging
poetry run pytest -s --pdb tests/test_specific.py::test_function
```

#### 2. Build Failures
```bash
# Check Docker build
docker build --no-cache -t debug-build .

# Inspect build layers
docker history debug-build
```

#### 3. Deployment Issues
```bash
# Check deployment logs
kubectl logs -f deployment/inkedup-bot

# Verify configuration
kubectl get configmap inkedup-config -o yaml
```

### Debugging Pipeline

#### 1. Enable Debug Logging
```yaml
- name: Debug info
  run: |
    echo "Runner OS: ${{ runner.os }}"
    echo "GitHub ref: ${{ github.ref }}"
    echo "Event name: ${{ github.event_name }}"
    env | sort
```

#### 2. SSH Debugging (Emergency Only)
```yaml
- name: Setup tmate session
  if: failure()
  uses: mxschmitt/action-tmate@v3
  with:
    limit-access-to-actor: true
```

#### 3. Artifact Collection
```yaml
- name: Upload test results
  if: always()
  uses: actions/upload-artifact@v3
  with:
    name: test-results
    path: |
      test-results/
      coverage-reports/
      benchmark.json
```

---

## Summary

The CI/CD pipeline provides:

1. **Comprehensive Testing**: Multi-level testing strategy
2. **Security Integration**: Multi-layer security scanning
3. **Automated Deployment**: Environment-specific deployment automation
4. **Quality Gates**: Automated quality assurance
5. **Monitoring**: Performance and health monitoring
6. **Best Practices**: Industry-standard DevOps practices

This pipeline ensures reliable, secure, and efficient software delivery for the InkedUp Polymarket Bot.

---

**Last Updated**: January 20, 2024  
**Version**: 1.0.0