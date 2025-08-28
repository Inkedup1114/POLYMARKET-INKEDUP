# Disaster Recovery Procedures - Quick Reference

*InkedUp Trading Bot - Emergency Response Guide*

## 🚨 EMERGENCY CONTACT

**CRITICAL INCIDENT HOTLINE**: Execute `bash scripts/disaster_recovery/respond_security_incident.sh` immediately for security breaches.

---

## Quick Recovery Commands

### Database Corruption
```bash
# Stop trading immediately
python -m inkedup_bot.cli cancel-all
pkill -f inkedup_bot

# Execute database recovery
bash scripts/disaster_recovery/recover_database_corruption.sh

# Verify recovery
python -m inkedup_bot.cli health --diagnostics
```

### Configuration Loss
```bash
# Execute configuration recovery
bash scripts/disaster_recovery/recover_configuration.sh

# Verify configuration
python -m inkedup_bot.cli config-status
```

### Application Crash
```bash
# Execute application recovery
bash scripts/disaster_recovery/recover_application_crash.sh

# Verify system health
python -m inkedup_bot.cli health --detailed
```

### Security Incident
```bash
# IMMEDIATE RESPONSE - Run this first
bash scripts/disaster_recovery/respond_security_incident.sh

# Follow the manual steps in the generated incident directory
# DO NOT restart trading until new credentials are configured
```

---

## Recovery Testing

### Monthly Tests
```bash
# Test database recovery
bash scripts/testing/test_disaster_recovery.sh database

# Test configuration recovery
bash scripts/testing/test_disaster_recovery.sh config

# Test application recovery  
bash scripts/testing/test_disaster_recovery.sh app

# Full disaster simulation
bash scripts/testing/test_disaster_recovery.sh full
```

### Monitoring
```bash
# Start automated monitoring
python scripts/monitoring/disaster_recovery_monitor.py

# Check monitoring status
tail -f /tmp/disaster_recovery_monitor.log
```

---

## Recovery Validation Checklist

After any recovery procedure:

- [ ] Database integrity: `sqlite3 bot_data.db "PRAGMA integrity_check;"`
- [ ] Configuration valid: `python -c "from inkedup_bot.config import BotConfig; BotConfig()"`
- [ ] Application healthy: `python -m inkedup_bot.cli health --diagnostics`
- [ ] Backup created: `python -m inkedup_bot.cli backup-create --backup-type=full`
- [ ] Trading readiness: Manual verification of account status

---

## Escalation Matrix

| Issue Severity | Response Time | Contact |
|---------------|---------------|---------|
| CRITICAL | Immediate | Emergency procedures + Management |
| HIGH | 15 minutes | Operations team |
| MEDIUM | 1 hour | Engineering team |

---

*See DISASTER_RECOVERY_PLAN.md for complete procedures and documentation.*