# PRP: Add Portfolio CLI Command

## 1. Feature Description
Implement a new CLI command `portfolio` that displays the current portfolio status, including total balance, active positions, and recent P&L using the Polymarket API.

---

## 2. Context & Documentation
- **Project Rules:** [`AGENT_RULES.md`](../AGENT_RULES.md)
- **Relevant Code:**
  - [`inkedup_bot/cli.py`](../inkedup_bot/cli.py) (main Typer app where command should be added)
  - [`inkedup_bot/order_client.py`](../inkedup_bot/order_client.py) (API client with positions() method)
  - [`inkedup_bot/config.py`](../inkedup_bot/config.py) (configuration management)
- **Examples:**
  - [`examples/cli_command_pattern.py`](../examples/cli_command_pattern.py) (CLI command pattern)
- **External Docs:**
  - [Polymarket API Documentation](https://docs.polymarket.com/)
  - [Rich Console Documentation](https://rich.readthedocs.io/en/stable/console.html)

---

## 3. Implementation Plan

1.  **Add portfolio command to `cli.py`:**
    - Import necessary modules (Rich components for formatting)
    - Create a new function `portfolio()` decorated with `@app.command()`
    - Follow the async pattern established in existing commands

2.  **Implement portfolio data fetching:**
    - Initialize OrderClient with BotConfig
    - Fetch positions using the existing `positions()` method
    - Calculate total portfolio value and P&L
    - Handle API errors gracefully with appropriate error messages

3.  **Create formatted display:**
    - Use Rich library components (Table, Panel, Console) for attractive output
    - Display portfolio summary (total value, number of positions)
    - Show individual positions in a table format
    - Use color coding for profit/loss indicators

4.  **Add error handling:**
    - Check if credentials are configured
    - Handle API connection failures
    - Display helpful error messages for common issues

---

## 4. Validation Plan

1.  **Unit Tests:**
    - **File:** `tests/test_cli.py` (create if doesn't exist)
    - **Tests to add:**
      - `test_portfolio_command_with_valid_config` - Test successful portfolio display
      - `test_portfolio_command_no_credentials` - Test error handling for missing credentials
      - `test_portfolio_command_api_error` - Test handling of API failures

2.  **Integration Test:**
    - **Manual Check:** Run `python -m inkedup_bot.cli portfolio` with valid credentials
    - Verify the output format and data accuracy
    - Test with invalid/missing credentials to ensure proper error handling

3.  **Code Quality:**
    - Run Black formatter on modified files
    - Run Ruff linter and ensure no new errors
    - Verify all new code has proper docstrings

---

## 5. Success Criteria

- [ ] `portfolio` command is added to `inkedup_bot/cli.py`
- [ ] Command successfully fetches and displays portfolio data when credentials are available
- [ ] Proper error handling for missing credentials and API failures
- [ ] Rich formatting is used for attractive console output
- [ ] Unit tests are added with good coverage of success and error scenarios
- [ ] All new code follows project conventions (docstrings, type hints, etc.)
- [ ] The `portfolio` command appears in the CLI `--help` output
- [ ] Manual testing confirms the command works as expected
