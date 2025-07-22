# Context Engineering Example: Feature Request

This is an example of a well-structured feature request using Context Engineering principles.

## FEATURE:
Add a `portfolio` CLI command that displays the current portfolio status, including total balance, active positions, and recent P&L using the Polymarket API. The command should:

1. **Portfolio Summary:** Show total portfolio value, number of active positions, and overall P&L
2. **Position Details:** Display each position in a formatted table with token ID, market name, size, current value, and P&L
3. **Rich Formatting:** Use Rich library components for attractive console output with color coding for profit/loss
4. **Error Handling:** Gracefully handle missing credentials, API failures, and empty portfolios
5. **Async Pattern:** Follow the established async pattern used in other CLI commands

## EXAMPLES:
Reference these specific files and patterns:

- **`examples/cli_command_pattern.py`:** Follow this EXACT pattern for:
  - Typer command structure with proper decorators
  - Async operation handling using `asyncio.run()`
  - Configuration loading with `BotConfig()`
  - Rich console formatting patterns
  - Error handling and user feedback

- **CLI Integration:** Study existing commands in `inkedup_bot/cli.py`:
  - How `positions()` command is structured
  - Error handling patterns for missing credentials
  - Rich formatting used in `status()` command

## DOCUMENTATION:
Include ALL relevant documentation for comprehensive context:

- **Project Standards:** [`AGENT_RULES.md`](AGENT_RULES.md) - Follow ALL coding conventions
- **API Client:** [`inkedup_bot/order_client.py`](inkedup_bot/order_client.py) - Use existing `positions()` method
- **Configuration:** [`inkedup_bot/config.py`](inkedup_bot/config.py) - BotConfig usage patterns
- **External APIs:**
  - [Polymarket API Documentation](https://docs.polymarket.com/) - Portfolio endpoints
  - [Rich Console Documentation](https://rich.readthedocs.io/en/stable/console.html) - Formatting options
  - [Rich Table Documentation](https://rich.readthedocs.io/en/stable/tables.html) - Table formatting

## OTHER CONSIDERATIONS:
Critical details that AI commonly misses:

**Authentication & Credentials:**
- Must check if `cfg.private_key` and `cfg.public_key` are configured
- Provide helpful error message if credentials missing: "Trading credentials not configured. Please set PUBLIC_KEY and PRIVATE_KEY environment variables."
- Should work gracefully even with missing credentials (show config status)

**Error Handling Patterns:**
- API connection failures should show user-friendly messages
- Empty portfolio should display "No active positions" rather than erroring
- Network timeouts should be handled with retry logic

**Rich Formatting Requirements:**
- Use `Table` for position display with columns: Token ID, Market, Side, Size, Value, P&L
- Use `Panel` for portfolio summary section
- Color coding: Green for profits, Red for losses, Yellow for warnings
- Include emoji indicators: ✅ for profits, ❌ for losses, ⚠️ for warnings

**Performance Considerations:**
- Portfolio data can be large - implement pagination if needed
- Cache position data briefly to avoid rate limiting
- Show loading indicator for slow API calls

**Testing Requirements:**
- Mock the OrderClient for unit tests
- Test scenarios: valid config, missing credentials, API errors, empty portfolio
- Integration test with actual API calls (manual verification)

**Common Gotchas:**
- Polymarket API returns positions in specific format - check existing `positions()` command
- Rich console formatting needs proper import statements
- Async functions must be wrapped with `asyncio.run()` in CLI commands
- Type hints are required for all function parameters and return values