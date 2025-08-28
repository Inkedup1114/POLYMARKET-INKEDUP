#!/usr/bin/env python3
"""
Disaster Recovery Monitoring System
Part of InkedUp Trading Bot Disaster Recovery Plan

This script monitors system health and triggers disaster recovery
procedures when critical failures are detected.
"""

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/disaster_recovery_monitor.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger('disaster_recovery_monitor')


class DisasterRecoveryMonitor:
    """Monitor system health and trigger disaster recovery when needed."""
    
    def __init__(self):
        self.monitoring = True
        self.check_interval = 30  # seconds
        self.failure_thresholds = {
            'consecutive_health_failures': 3,
            'database_corruption_detected': 1,
            'memory_threshold_mb': 2048,
            'disk_threshold_percent': 90,
            'response_timeout_seconds': 45
        }
        
        self.failure_counts = {
            'health_check_failures': 0,
            'database_failures': 0,
            'memory_warnings': 0,
            'response_timeouts': 0
        }
        
        self.last_successful_health_check = datetime.now()
        self.recovery_in_progress = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        log.info(f"Received signal {signum}, shutting down monitor...")
        self.monitoring = False
    
    async def start_monitoring(self):
        """Start the disaster recovery monitoring loop."""
        log.info("Starting disaster recovery monitoring...")
        
        while self.monitoring:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                log.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)
        
        log.info("Disaster recovery monitoring stopped")
    
    async def _perform_health_checks(self):
        """Perform comprehensive health checks."""
        log.debug("Performing health checks...")
        
        checks = [
            self._check_application_health(),
            self._check_database_integrity(),
            self._check_system_resources(),
            self._check_configuration_validity(),
            self._check_api_connectivity()
        ]
        
        results = await asyncio.gather(*checks, return_exceptions=True)
        
        # Process results and determine if recovery is needed
        critical_failures = []
        warnings = []
        
        for i, result in enumerate(results):
            check_name = ['application', 'database', 'resources', 'configuration', 'api'][i]
            
            if isinstance(result, Exception):
                log.error(f"Health check {check_name} failed with exception: {result}")
                critical_failures.append(check_name)
            elif isinstance(result, dict):
                if result.get('status') == 'critical':
                    critical_failures.append(check_name)
                elif result.get('status') == 'warning':
                    warnings.append(check_name)
        
        # Log results
        if critical_failures:
            log.warning(f"Critical failures detected: {critical_failures}")
            await self._handle_critical_failures(critical_failures)
        elif warnings:
            log.info(f"Warnings detected: {warnings}")
            await self._handle_warnings(warnings)
        else:
            log.debug("All health checks passed")
            self._reset_failure_counts()
    
    async def _check_application_health(self) -> Dict:
        """Check application health via CLI."""
        try:
            start_time = time.time()
            
            # Run health check with timeout
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-m', 'inkedup_bot.cli', 'health', '--detailed',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=self.failure_thresholds['response_timeout_seconds']
            )
            
            stdout, stderr = await proc.communicate()
            response_time = time.time() - start_time
            
            if proc.returncode == 0:
                self.last_successful_health_check = datetime.now()
                return {
                    'status': 'ok',
                    'response_time': response_time,
                    'details': 'Application health check passed'
                }
            else:
                self.failure_counts['health_check_failures'] += 1
                return {
                    'status': 'critical',
                    'error': stderr.decode() if stderr else 'Health check failed',
                    'response_time': response_time
                }
                
        except asyncio.TimeoutError:
            self.failure_counts['response_timeouts'] += 1
            return {
                'status': 'critical',
                'error': 'Health check timeout',
                'response_time': self.failure_thresholds['response_timeout_seconds']
            }
        except Exception as e:
            self.failure_counts['health_check_failures'] += 1
            return {
                'status': 'critical',
                'error': f'Health check exception: {e}'
            }
    
    async def _check_database_integrity(self) -> Dict:
        """Check database integrity."""
        try:
            if not os.path.exists('bot_data.db'):
                return {
                    'status': 'critical',
                    'error': 'Database file not found'
                }
            
            # Check database integrity
            proc = await asyncio.create_subprocess_exec(
                'sqlite3', 'bot_data.db', 'PRAGMA integrity_check;',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=30
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0 and b'ok' in stdout:
                return {
                    'status': 'ok',
                    'details': 'Database integrity check passed'
                }
            else:
                self.failure_counts['database_failures'] += 1
                return {
                    'status': 'critical',
                    'error': f'Database integrity check failed: {stderr.decode() if stderr else "Unknown error"}'
                }
                
        except Exception as e:
            self.failure_counts['database_failures'] += 1
            return {
                'status': 'critical',
                'error': f'Database check exception: {e}'
            }
    
    async def _check_system_resources(self) -> Dict:
        """Check system resource usage."""
        try:
            # Check memory usage
            proc = await asyncio.create_subprocess_exec(
                'free', '-m',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                return {
                    'status': 'warning',
                    'error': 'Could not check memory usage'
                }
            
            # Parse memory info
            lines = stdout.decode().strip().split('\n')
            mem_line = lines[1].split()
            total_mem = int(mem_line[1])
            used_mem = int(mem_line[2])
            mem_percent = (used_mem / total_mem) * 100
            
            # Check disk usage
            proc = await asyncio.create_subprocess_exec(
                'df', '.',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            disk_percent = 0
            if proc.returncode == 0:
                lines = stdout.decode().strip().split('\n')
                if len(lines) >= 2:
                    disk_info = lines[1].split()
                    disk_percent = int(disk_info[4].rstrip('%'))
            
            # Evaluate thresholds
            status = 'ok'
            issues = []
            
            if used_mem > self.failure_thresholds['memory_threshold_mb']:
                status = 'critical'
                issues.append(f'High memory usage: {used_mem}MB')
                self.failure_counts['memory_warnings'] += 1
            
            if disk_percent > self.failure_thresholds['disk_threshold_percent']:
                status = 'warning'
                issues.append(f'High disk usage: {disk_percent}%')
            
            return {
                'status': status,
                'details': {
                    'memory_used_mb': used_mem,
                    'memory_percent': mem_percent,
                    'disk_percent': disk_percent,
                    'issues': issues
                }
            }
            
        except Exception as e:
            return {
                'status': 'warning',
                'error': f'Resource check exception: {e}'
            }
    
    async def _check_configuration_validity(self) -> Dict:
        """Check configuration validity."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, '-c', 'from inkedup_bot.config import BotConfig; BotConfig()',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                timeout=10
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                return {
                    'status': 'ok',
                    'details': 'Configuration validation passed'
                }
            else:
                return {
                    'status': 'critical',
                    'error': f'Configuration validation failed: {stderr.decode() if stderr else "Unknown error"}'
                }
                
        except Exception as e:
            return {
                'status': 'critical',
                'error': f'Configuration check exception: {e}'
            }
    
    async def _check_api_connectivity(self) -> Dict:
        """Check API connectivity."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'curl', '-s', '--max-time', '10', 'https://clob.polymarket.com/ping',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                return {
                    'status': 'ok',
                    'details': 'API connectivity check passed'
                }
            else:
                return {
                    'status': 'warning',
                    'error': f'API connectivity check failed: {stderr.decode() if stderr else "Connection failed"}'
                }
                
        except Exception as e:
            return {
                'status': 'warning',
                'error': f'API connectivity exception: {e}'
            }
    
    async def _handle_critical_failures(self, failures: List[str]):
        """Handle critical system failures."""
        if self.recovery_in_progress:
            log.warning("Recovery already in progress, skipping new recovery trigger")
            return
        
        # Check if thresholds are met
        if self.failure_counts['health_check_failures'] >= self.failure_thresholds['consecutive_health_failures']:
            log.critical("Critical failure threshold reached, triggering disaster recovery")
            await self._trigger_disaster_recovery(failures)
        elif 'database' in failures and self.failure_counts['database_failures'] >= self.failure_thresholds['database_corruption_detected']:
            log.critical("Database corruption detected, triggering database recovery")
            await self._trigger_database_recovery()
        elif 'resources' in failures and self.failure_counts['memory_warnings'] >= 2:
            log.critical("Memory exhaustion detected, triggering application recovery")
            await self._trigger_application_recovery()
    
    async def _handle_warnings(self, warnings: List[str]):
        """Handle system warnings."""
        log.warning(f"System warnings detected: {warnings}")
        
        # Log warning details for monitoring
        warning_log = {
            'timestamp': datetime.now().isoformat(),
            'warnings': warnings,
            'failure_counts': self.failure_counts
        }
        
        with open('/tmp/disaster_recovery_warnings.json', 'a') as f:
            json.dump(warning_log, f)
            f.write('\n')
    
    async def _trigger_disaster_recovery(self, failures: List[str]):
        """Trigger full disaster recovery."""
        log.critical("TRIGGERING FULL DISASTER RECOVERY")
        self.recovery_in_progress = True
        
        try:
            # Create incident report
            incident_report = {
                'timestamp': datetime.now().isoformat(),
                'incident_type': 'automatic_disaster_recovery',
                'failures': failures,
                'failure_counts': self.failure_counts,
                'trigger': 'monitoring_system'
            }
            
            with open(f'/tmp/disaster_incident_{int(time.time())}.json', 'w') as f:
                json.dump(incident_report, f, indent=2)
            
            # Execute recovery based on primary failure
            if 'database' in failures:
                await self._execute_script('scripts/disaster_recovery/recover_database_corruption.sh')
            elif 'application' in failures:
                await self._execute_script('scripts/disaster_recovery/recover_application_crash.sh')
            elif 'configuration' in failures:
                await self._execute_script('scripts/disaster_recovery/recover_configuration.sh')
            else:
                # General application recovery
                await self._execute_script('scripts/disaster_recovery/recover_application_crash.sh')
            
            log.info("Disaster recovery procedure completed")
            
        except Exception as e:
            log.error(f"Disaster recovery failed: {e}")
        finally:
            self.recovery_in_progress = False
    
    async def _trigger_database_recovery(self):
        """Trigger database-specific recovery."""
        log.critical("TRIGGERING DATABASE RECOVERY")
        self.recovery_in_progress = True
        
        try:
            await self._execute_script('scripts/disaster_recovery/recover_database_corruption.sh')
            log.info("Database recovery procedure completed")
        except Exception as e:
            log.error(f"Database recovery failed: {e}")
        finally:
            self.recovery_in_progress = False
    
    async def _trigger_application_recovery(self):
        """Trigger application-specific recovery."""
        log.critical("TRIGGERING APPLICATION RECOVERY")
        self.recovery_in_progress = True
        
        try:
            await self._execute_script('scripts/disaster_recovery/recover_application_crash.sh')
            log.info("Application recovery procedure completed")
        except Exception as e:
            log.error(f"Application recovery failed: {e}")
        finally:
            self.recovery_in_progress = False
    
    async def _execute_script(self, script_path: str):
        """Execute a disaster recovery script."""
        log.info(f"Executing recovery script: {script_path}")
        
        proc = await asyncio.create_subprocess_exec(
            'bash', script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        stdout, _ = await proc.communicate()
        
        # Log script output
        script_log = f'/tmp/recovery_script_{int(time.time())}.log'
        with open(script_log, 'w') as f:
            f.write(stdout.decode())
        
        if proc.returncode != 0:
            log.error(f"Recovery script failed with return code {proc.returncode}")
            log.error(f"Script output logged to: {script_log}")
            raise RuntimeError(f"Recovery script {script_path} failed")
        else:
            log.info(f"Recovery script completed successfully. Output: {script_log}")
    
    def _reset_failure_counts(self):
        """Reset failure counts after successful checks."""
        for key in self.failure_counts:
            if self.failure_counts[key] > 0:
                self.failure_counts[key] = max(0, self.failure_counts[key] - 1)
    
    def get_status(self) -> Dict:
        """Get current monitoring status."""
        return {
            'monitoring': self.monitoring,
            'recovery_in_progress': self.recovery_in_progress,
            'last_successful_health_check': self.last_successful_health_check.isoformat(),
            'failure_counts': self.failure_counts,
            'failure_thresholds': self.failure_thresholds,
            'check_interval': self.check_interval
        }


async def main():
    """Main monitoring function."""
    monitor = DisasterRecoveryMonitor()
    
    log.info("Disaster Recovery Monitor starting...")
    
    try:
        await monitor.start_monitoring()
    except KeyboardInterrupt:
        log.info("Monitoring interrupted by user")
    except Exception as e:
        log.error(f"Monitoring failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())