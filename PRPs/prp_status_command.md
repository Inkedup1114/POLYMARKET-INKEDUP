# PRP: Add Status CLI Command

## 1. Feature Description
Implement a new CLI command `status` that displays the bot's current operational status, configuration summary, and recent activity information without requiring trading credentials.

---

## 2. Context & Documentation
- **Project Rules:** [`AGENT_RULES.md`](../AGENT_RULES.md)
- **Relevant Code:**
  - [`inkedup_bot/cli.py`](../inkedup_bot/cli.py) (main Typer app where command should be added)
  - [`inkedup_bot/config.py`](../inkedup_bot/config.py) (configuration management)
  - [`inkedup_bot/state.py`](../inkedup_bot/state.py) (state and activity tracking)
  - [`inkedup_bot/database.py`](../inkedup_bot/database.py) (database access for recent activity)
- **Examples:**
  - [`examples/cli_command_pattern.py`](../examples/cli_command_pattern.py) (CLI command pattern)
- **External Docs:**
  - [Typer Documentation](https://typer.tiangolo.com/)
  - [Rich Console Documentation](https://rich.readthedocs.io/en/stable/console.html)

---

## 3. Implementation Plan

1.  **Add status command to `cli.py`:**
    - Import Rich components (Table, Panel, Console) for formatted output
    - Create a new function `status()` decorated with `@app.command()`
    - Follow the async pattern established in existing commands
    - Add optional verbose flag for detailed output

2.  **Implement bot process detection:**
    - Check if any bot processes are currently running (scanner, snapshot service)
    - Use process detection or PID file checking
    - Return appropriate status indicators (running/stopped/unknown)

3.  **Display configuration summary:**
    - Load BotConfig and display key settings (API endpoints, enabled features)
    - Show risk limits and trading parameters
    - Mask sensitive information like private keys
    - Use different formatting for enabled vs disabled features

4.  **Show recent activity summary:**
    - Query database for recent orders, trades, and snapshots (last 24 hours)
    - Display summary statistics (number of orders, total volume, etc.)
    - Handle gracefully when database is unavailable or empty
    - Show last activity timestamp if available

5.  **Implement proper exit codes:**
    - Return 0 for healthy status
    - Return 1 for warning conditions (no recent activity, missing config)
    - Return 2 for error conditions (database unavailable, critical config missing)

6.  **Add error handling:**
    - Handle database connection failures gracefully
    - Work without trading credentials (show config status only)
    - Display helpful error messages for common issues

---

## 4. Validation Plan

1.  **Unit Tests:**
    - **File:** `tests/test_cli.py` (create new file)
    - **Description:** Test status command with mocked components
    - Test scenarios: healthy status, missing config, database errors
    - Verify exit codes for different conditions
    - Test output formatting and content

2.  **Integration Tests:**
    - **Manual Check:** Run `python -m inkedup_bot.cli status` with valid configuration
    - Test with missing/invalid configuration files
    - Test with empty database vs database with recent activity
    - Verify proper exit codes for scripting scenarios

3.  **Code Quality:**
    - Run Black formatter on `inkedup_bot/cli.py` and `tests/test_cli.py`
    - Run linter and ensure no errors
    - Verify all new code has proper docstrings and type hints

---

## 5. Success Criteria

- [ ] `status` command is added to `inkedup_bot/cli.py` following the established pattern
- [ ] Command displays bot running status (process detection)
- [ ] Configuration summary is shown with key settings and feature flags
- [ ] Recent activity summary is displayed when database is available
- [ ] Proper exit codes are returned for different status conditions (0/1/2)
- [ ] Command works without requiring trading credentials
- [ ] Rich formatting is used for attractive and readable console output
- [ ] Comprehensive error handling for missing config and database issues
- [ ] Unit tests are added in `tests/test_cli.py` with good coverage
- [ ] All new code follows project conventions (docstrings, type hints, formatting)
- [ ] The `status` command appears in the CLI `--help` output
- [ ] Manual testing confirms all functionality works as expected
- [ ] Exit codes work correctly for monitoring and scripting use cases
