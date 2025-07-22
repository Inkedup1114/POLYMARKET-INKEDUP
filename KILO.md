# Kilo Code Project Guidelines

This document contains the global rules, conventions, and patterns that the Kilo Code AI assistant must follow for this project. Adherence to these guidelines is mandatory for all tasks.

## 1. Project Awareness & Planning
- **Review Context:** Before starting any task, review this document (`KILO.md`), the `README.md`, the current TODO list, and any relevant files in the `PRPs/` or `examples/` directories.
- **Clarification:** If the user's request is ambiguous or lacks detail, ask clarifying questions before proceeding. Do not make assumptions about implementation details.
- **Task Breakdown:** For complex requests, break down the problem into smaller, manageable steps and update the TODO list accordingly.

## 2. Code Structure & Conventions
- **File Size:** Keep files focused and modular. Avoid creating monolithic files. As a general rule, files should not exceed 300 lines of code unless absolutely necessary for the framework or pattern being used.
- **Module Organization:** Group related functionality into modules or packages. Follow existing project structure. If a new module is created, include an `__init__.py` if it's a Python package.
- **Naming Conventions:** Use clear and descriptive names for variables, functions, classes, and files. Follow language-specific conventions (e.g., PEP 8 for Python, camelCase for JavaScript).

## 3. Testing Requirements
- **Unit Tests:** All new features or bug fixes must be accompanied by corresponding unit tests.
- **Test Location:** Place tests in the `tests/` directory, mirroring the structure of the source code. For example, a function in `inkedup_bot/utils.py` should be tested in `tests/test_utils.py`.
- **Test Coverage:** Aim for high test coverage. Mocks should be used where appropriate to isolate units of code.

## 4. Style & Formatting
- **Language Preferences:** Default to Python unless otherwise specified. All Python code must be formatted using a standard formatter like Black.
- **Clarity and Simplicity:** Write code that is easy to read and understand. Favor clear, straightforward logic over overly complex or "clever" solutions.

## 5. Documentation Standards
- **Docstrings:** All public modules, functions, classes, and methods must have docstrings explaining their purpose, arguments, and return values. Follow a standard format like Google Style for Python docstrings.
- **Inline Comments:** Use inline comments to explain complex or non-obvious parts of the code. Do not add comments for code that is self-explanatory.

## 6. Trading Bot Specific Guidelines
- **Risk Management:** All trading strategies must implement proper risk management controls. Never exceed configured position limits (global_risk_cap, per_market_risk_cap, per_outcome_risk_cap).
- **Error Handling:** API calls to Polymarket must include proper error handling and retry logic for transient failures.
- **Logging:** Use structured logging for all trading operations. Include context like market IDs, order IDs, and amounts.
- **Testing with Mock Data:** Trading strategies should be testable with mock market data. Never execute real trades in tests.
- **Strategy Pattern:** All new trading strategies must inherit from base Strategy class and implement the `evaluate()` method returning `TradingSignal` objects.
- **Signal Processing:** All trading actions must go through the `TradingEngine.process_signal()` method for proper risk checking and execution.
- **Market Data:** Use the Scanner's market data format with `market_snapshots` containing `yes_book` and `no_book` structures.

## 7. Environment & Configuration
- **Environment Variables:** Use environment variables for all sensitive configuration (API keys, secrets). Reference `.env.template` for available options.
- **Configuration Files:** Non-sensitive configuration should use the `config.py` module with BotConfig dataclass.
- **Database:** Use SQLite for local data persistence. All database operations should be async using aiosqlite.
- **CLI Commands:** Follow the Typer pattern established in `cli.py` and reference `examples/cli_command_pattern.py`.
- **Rich Output:** Use Rich library components (Table, Panel, Console) for formatted CLI output.

## 8. Agent-Agnostic Context Engineering
This project supports both GitHub Copilot and Kilo Code workflows:
- **PRP Generation:** Use either `.copilot/prompts/generate-prp.md` or `/generate-prp` command
- **PRP Execution:** Use either `.copilot/prompts/execute-prp.md` or `/execute-prp` command
- **Examples:** Reference code in `examples/` directory for patterns and conventions
- **Documentation:** Keep all Agent Rules, examples, and PRPs up to date

## 9. Project-Specific Patterns
- **Module Structure:** Follow the established package structure in `inkedup_bot/` with strategies in `strategies/` subdirectory
- **Signal Flow:** Market data → Scanner → Strategies → TradingEngine → OrderClient → Database
- **Configuration Keys:** Reference actual environment variables from `.env.template` (e.g., `POLYMARKET_API_BASE`, `GLOBAL_RISK_CAP_USD`)
- **Database Schema:** Use existing tables: orders, trades, positions, market_snapshots, risk_events
- **CLI Task Integration:** New commands should integrate with VS Code tasks defined in `.vscode/tasks.json`
- **Import Patterns:** Use relative imports within the package (`from .config import BotConfig`)
- **Async Patterns:** All strategy evaluation and database operations should be async-compatible