# PRP: Enhanced Status CLI Command Implementation

## 1. Feature Description
Implement a comprehensive `status` CLI command that provides operational status, configuration summary, and recent activity information for the InkedUp bot. The command should serve both human operators and automated monitoring systems with appropriate exit codes and rich formatted output.

**Key Requirements:**
- Show if bot scanner is currently running
- Display configuration information (API endpoints, enabled features)
- Show recent activity summary when available
- Return appropriate exit codes for scripting (0=healthy, 1=warning, 2=error)
- Work without requiring trading credentials for basic status
- Use Rich formatting for human-readable output
- Include health check capabilities for monitoring systems

---

## 2. Context & Documentation  
**Complete context engineering - ALL relevant files, patterns, documentation, and resources.**

- **Project Rules:** [`AGENT_RULES.md`](../AGENT_RULES.md) - Follow ALL coding standards and conventions
  - File size limit: 300 lines maximum unless framework requires more
  - PEP 8 naming conventions
  - Comprehensive unit testing requirements
  - Type hints for all function parameters and returns

- **Relevant Code Files:**
  - `inkedup_bot/cli.py` - Existing CLI structure and status command (lines 1-50 show imports and structure)
  - `inkedup_bot/config.py` - BotConfig pattern for accessing configuration
  - `inkedup_bot/database.py` - DatabaseManager for checking database connectivity
  - `inkedup_bot/scanner.py` - Scanner service for checking if bot is running
  - `inkedup_bot/state.py` - StateManager for accessing recent activity data

- **Code Patterns to Follow:**
  - `examples/cli_command_pattern.py` - CLI command structure with Typer, async handling, Rich output
  - Existing `status()` command in `inkedup_bot/cli.py` - Current implementation patterns
  - Use `rich.console.Console`, `rich.table.Table`, `rich.panel.Panel` for formatting
  - Follow async pattern: `asyncio.run(run())` for async operations

- **External Documentation:**
  - [Typer CLI Framework](https://typer.tiangolo.com/) - Command structure and options
  - [Rich Library](https://rich.readthedocs.io/) - Console formatting and tables
  - [AsyncIO Best Practices](https://docs.python.org/3/library/asyncio.html) - Async operation patterns

- **Gotchas & Common Pitfalls:**
  - Status command already exists in `cli.py` - need to enhance, not create new
  - Database connectivity checks should handle connection failures gracefully
  - Don't require trading credentials for basic status (handle AuthenticationError)
  - Exit codes must be consistent (0=success, 1=warning, 2=error)
  - Rich formatting should degrade gracefully in non-terminal environments

---

## 3. Implementation Plan
**Detailed, step-by-step implementation with validation checkpoints.**

### Step 1: Analyze Current Status Command
- **Action:** Examine existing `status()` command in `inkedup_bot/cli.py`
- **Files to Review:** `inkedup_bot/cli.py` (lines 25-100 approximately)
- **Pattern:** Understand current implementation and identify enhancement opportunities
- **Validation:** `grep -n "def status" inkedup_bot/cli.py` to locate existing function

### Step 2: Enhance Status Command Implementation
- **Action:** Extend existing status command with comprehensive health checks
- **Files to Modify:** `inkedup_bot/cli.py` (enhance existing status function)
- **Code Patterns:** Follow `examples/cli_command_pattern.py` for async operations and Rich formatting
- **Key Components to Add:**
  - Database connectivity check using `DatabaseManager`
  - Scanner service status using `Scanner` class
  - Configuration validation using `BotConfig`
  - Recent activity summary using `StateManager`
  - Proper exit code handling (0/1/2)
- **Validation:** `python -m inkedup_bot.cli status --help` shows updated help text

### Step 3: Implement Health Check Functions
- **Action:** Add helper functions for individual health checks
- **Pattern:** Create separate async functions for each health check component
- **Functions to Implement:**
  - `_check_database_health() -> tuple[bool, str]`
  - `_check_scanner_status() -> tuple[bool, str]` 
  - `_check_config_validity() -> tuple[bool, str]`
  - `_get_recent_activity() -> dict`
- **Validation:** Each function should handle exceptions and return consistent format

### Step 4: Implement Rich Formatted Output
- **Action:** Create comprehensive status display using Rich components
- **Pattern:** Use `Table`, `Panel`, and `Console` from Rich library
- **Components:**
  - System status table (database, scanner, config)
  - Configuration summary panel
  - Recent activity table (if available)
  - Color coding: green=healthy, yellow=warning, red=error
- **Validation:** Output should be readable both in terminal and when piped

### Step 5: Add Proper Exit Code Logic
- **Action:** Implement exit code determination based on health checks
- **Logic:**
  - Exit 0: All systems healthy
  - Exit 1: Warning conditions (no recent activity, non-critical config issues)
  - Exit 2: Error conditions (database down, critical config missing)
- **Pattern:** Use `typer.Exit(code)` for proper exit handling
- **Validation:** Test with `echo $?` after running command in different scenarios

### Step 6: Error Handling and Graceful Degradation
- **Action:** Implement comprehensive error handling
- **Pattern:** Try/except blocks for each health check, continue on individual failures
- **Error Scenarios:**
  - Database connection timeout
  - Missing configuration files
  - Authentication failures (should not prevent basic status)
  - Scanner service unavailable
- **Validation:** Test error scenarios and verify graceful handling

### Step 7: Unit Tests Implementation
- **Action:** Create comprehensive unit tests
- **Files to Create/Modify:** `tests/test_cli.py` (add status command tests)
- **Test Cases:**
  - Healthy system status (exit code 0)
  - Warning conditions (exit code 1)
  - Error conditions (exit code 2)
  - Database connectivity failure handling
  - Rich output formatting verification
  - Verbose vs non-verbose output
- **Pattern:** Use pytest with mocking for external dependencies
- **Validation:** `python -m pytest tests/test_cli.py::test_status_command -v`

---

## 4. Success Criteria Checklist

### Functional Requirements ✓
- [ ] Status command shows database connectivity status
- [ ] Status command shows scanner service status  
- [ ] Status command displays configuration summary
- [ ] Status command shows recent activity when available
- [ ] Command works without trading credentials for basic checks
- [ ] Proper exit codes returned (0=healthy, 1=warning, 2=error)
- [ ] Verbose option provides additional detail

### Code Quality Requirements ✓
- [ ] Follows PEP 8 naming conventions
- [ ] All functions have type hints
- [ ] Error handling for all external dependencies
- [ ] File size remains under 300 lines (or justified if larger)
- [ ] Rich formatting for human-readable output
- [ ] Async operations use proper patterns

### Testing Requirements ✓
- [ ] Unit tests cover all major code paths
- [ ] Tests verify exit code behavior
- [ ] Tests mock external dependencies (database, scanner)
- [ ] Tests verify Rich output formatting
- [ ] Edge cases and error conditions tested
- [ ] Minimum 80% test coverage for new code

### Documentation Requirements ✓
- [ ] Function docstrings follow project standards
- [ ] CLI help text is clear and comprehensive
- [ ] Code comments explain complex logic
- [ ] Type hints provide clear interface documentation

### Integration Requirements ✓
- [ ] Works with existing CLI framework
- [ ] Integrates with current BotConfig system
- [ ] Uses established DatabaseManager patterns
- [ ] Follows existing logging patterns
- [ ] Compatible with current project structure

---

## 5. Validation Commands

### Code Quality Validation
```bash
# Format code
python -m black inkedup_bot/cli.py tests/test_cli.py

# Lint code  
python -m ruff check inkedup_bot/cli.py tests/test_cli.py

# Type checking
python -m mypy inkedup_bot/cli.py
```

### Testing Validation
```bash
# Run specific status command tests
python -m pytest tests/test_cli.py::test_status_command -v

# Run all CLI tests
python -m pytest tests/test_cli.py -v

# Check test coverage
python -m pytest tests/test_cli.py --cov=inkedup_bot.cli --cov-report=term-missing
```

### Manual Testing Validation
```bash
# Test basic status
python -m inkedup_bot.cli status

# Test verbose status
python -m inkedup_bot.cli status --verbose

# Test exit codes
python -m inkedup_bot.cli status; echo "Exit code: $?"

# Test help output
python -m inkedup_bot.cli status --help
```

### Integration Testing
```bash
# Test with bot dependencies
python -m pytest tests/test_integration.py -k status

# Test CLI integration
python -m pytest tests/test_cli.py -v
```

---

## 6. Implementation Notes

### Current Implementation Status
The status command already exists in `inkedup_bot/cli.py`. This PRP focuses on enhancing the existing implementation rather than creating from scratch.

### Key Integration Points
- **BotConfig:** Use for configuration access and validation
- **DatabaseManager:** For database connectivity checks
- **Scanner:** For checking if bot services are running
- **StateManager:** For accessing recent activity data
- **Rich:** For formatted console output

### Performance Considerations
- Health checks should complete within 5 seconds
- Database connectivity check should timeout appropriately
- Avoid expensive operations in basic status check
- Cache configuration validation results when possible

### Monitoring Integration
The enhanced status command should be suitable for:
- Shell script health checks (`if [ $? -eq 0 ]`)
- Systemd service monitoring
- External monitoring tools (Nagios, Prometheus)
- Container health checks (Docker/Kubernetes)
