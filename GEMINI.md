# Gemini Workspace Configuration

This document outlines the project setup and provides instructions for using Gemini to efficiently work on the `polymarket-inkedup` project.

## Project Overview

The `polymarket-inkedup` project is a Python-based asynchronous trading bot for the Polymarket prediction market. It is designed to be extensible with different trading strategies and includes a robust set of tools for development, testing, and deployment.

### Key Technologies

- **Programming Language:** Python 3.12
- **Main Application Framework:** Typer (for CLI)
- **Core Libraries:**
    - `py-clob-client`: For interacting with the Polymarket CLOB (Central Limit Order Book).
    - `aiohttp`: For asynchronous HTTP requests.
    - `SQLAlchemy`: For database interactions (with `aiosqlite` and `asyncpg`).
    - `Pydantic`: For data validation and settings management.
    - `Alembic`: For database migrations.
- **Development Tools:**
    - `pytest`: For running tests.
    - `ruff`: For linting.
    - `black`: For code formatting.
    - `mypy`: For static type checking.
    - `Docker`: For containerization.

## Development Workflow

The project uses a standard Python development workflow with a virtual environment, dependency management, and a suite of quality assurance tools.

### Setup

To set up the development environment, run the following command:

```bash
make install
```

This will create a virtual environment in `.venv` and install all the required dependencies from `requirements.txt`.

### Running the Bot

The main entry point for the bot is through the `inkedup_bot.cli` module. You can run the bot using the following commands:

- **Run a one-off scan:**
  ```bash
  python -m inkedup_bot.cli once
  ```
- **Start the continuous scanning loop:**
  ```bash
  python -m inkedup_bot.cli scan --interval 30
  ```

### Testing

The project has a comprehensive test suite located in the `tests/` directory. To run the tests, use the following command:

```bash
make test
```

This command will run `pytest` with the appropriate configurations as defined in `pyproject.toml`.

### Linting and Formatting

The project uses `ruff` for linting and `black` for code formatting.

- **To run the linter:**
  ```bash
  ruff check .
  ```
- **To format the code:**
  ```bash
  black .
  ```

## Project Structure

- `inkedup_bot/`: The main application source code.
  - `cli.py`: The command-line interface entry point.
  - `scanner.py`: Core logic for scanning markets.
  - `strategies/`: Different trading strategies.
  - `models/`: Pydantic and SQLAlchemy models.
  - `db/`: Database-related modules.
- `tests/`: Unit and integration tests.
- `examples/`: Example usage scripts.
- `docs/`: Project documentation.
- `pyproject.toml`: Project metadata and tool configuration.
- `requirements.txt`: Project dependencies.
- `Makefile`: Shortcuts for common development tasks.
- `Dockerfile` and `docker-compose.yml`: For containerized deployments.

## How to Use Gemini in This Project

### Understanding the Code

To understand a specific part of the codebase, you can ask Gemini to explain a file or a directory. For example:

> "Explain the purpose of the `inkedup_bot/scanner.py` file."

### Modifying the Code

When you want to modify the code, clearly state your requirements. Gemini will analyze the relevant files, propose changes, and apply them. For example:

> "Add a new CLI command to show the bot's current status."

### Creating New Features

To create a new feature, describe the feature in detail. Gemini will create a plan, write the code, and add tests. For example:

> "Implement a new trading strategy that follows the 'buy low, sell high' principle."

By following these guidelines, you can effectively use Gemini to accelerate your development process in the `polymarket-inkedup` project.
