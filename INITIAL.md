## FEATURE:
Add a `status` CLI command that shows if the bot is running and provides basic system status information.

The status command should:
1. Show if the bot scanner is currently running
2. Display basic configuration information (API endpoints, enabled features)
3. Show recent activity summary if available
4. Return appropriate exit codes for scripting

## EXAMPLES:
Use `cli_command_pattern.py` as the pattern for implementing the new CLI command. The status command should follow the same structure with proper async handling and Rich output formatting.

## DOCUMENTATION:
- Reference `AGENT_RULES.md` for project standards
- Use the existing CLI structure in `inkedup_bot/cli.py`
- Follow the BotConfig pattern for accessing configuration
- Include unit tests in `tests/test_cli.py`

## OTHER CONSIDERATIONS:
- Should work without requiring trading credentials for basic status
- Use Rich for formatted output similar to other CLI commands
- Include proper error handling for when bot services are unavailable
- Consider adding health check endpoints that could be used by monitoring systems