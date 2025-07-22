# Context Engineering Rules for InkedUp Bot

This document contains the global rules, conventions, and patterns that GitHub Copilot Chat, Kilo Code, and other AI assistants must follow for this project. This is a **Context Engineering** system, not just prompt engineering.

## Context Engineering vs Prompt Engineering

**Prompt Engineering:** Focuses on clever wording and specific phrasing (like giving someone a sticky note)
**Context Engineering:** A complete system providing comprehensive context including documentation, examples, rules, patterns, and validation (like writing a full screenplay)

## 1. Project Awareness & Planning (Context Engineering)
- **Comprehensive Context Review:** Before starting any task, systematically review:
  - This document (`AGENT_RULES.md`) for project-wide standards
  - The `README.md` for project overview and setup
  - Current `TODO.md` for ongoing tasks and priorities
  - Relevant files in `PRPs/` directory for implementation blueprints
  - Code patterns in `examples/` directory for established conventions
  - Related source files to understand existing architecture
- **Context-Driven Clarification:** If the user's request lacks context, ask clarifying questions while referencing existing patterns and examples from the codebase.
- **Structured Task Breakdown:** For complex requests, create detailed implementation plans following the PRP (Product Requirements Prompt) methodology.

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
- **Risk Management:** All trading strategies must implement proper risk management controls. Never exceed configured position limits.
- **Error Handling:** API calls to Polymarket must include proper error handling and retry logic for transient failures.
- **Logging:** Use structured logging for all trading operations. Include context like market IDs, order IDs, and amounts.
- **Testing with Mock Data:** Trading strategies should be testable with mock market data. Never execute real trades in tests.

## 7. Environment & Configuration
- **Environment Variables:** Use environment variables for all sensitive configuration (API keys, secrets).
- **Configuration Files:** Non-sensitive configuration should use the `config.py` module.
- **Database:** Use SQLite for local data persistence. All database operations should be async.

## 8. Context Engineering Workflow for GitHub Copilot & Kilo Code

This project uses a comprehensive Context Engineering system instead of simple prompt engineering:

### Context Engineering Components:
- **PRPs (Product Requirements Prompts):** Comprehensive implementation blueprints (similar to PRDs but AI-optimized)
- **Examples Directory:** Code patterns and conventions (`examples/`)
- **Agent Rules:** This document with project-wide standards
- **Validation Gates:** Test commands and quality checks that must pass
- **Documentation Context:** API docs, library guides, and MCP server resources

### GitHub Copilot Chat Workflow:
1. **Generate PRP:** Use `.copilot/prompts/generate-prp.md` with your feature request
2. **Execute PRP:** Use `.copilot/prompts/execute-prp.md` with the generated PRP
3. **Validate:** Run tests and quality checks defined in the PRP
4. **Iterate:** Fix issues until all success criteria are met

### Kilo Code Extension Commands:
- `/generate-prp [feature-request-file]` - Generate comprehensive implementation blueprint
- `/execute-prp [prp-file]` - Execute PRP to implement feature with validation
- `/context-check` - Verify all context engineering components are up to date

### Key Principles:
- **Comprehensive Context:** Every task includes full context, not just the immediate request
- **Pattern Following:** Reference `examples/` directory for established conventions
- **Validation-Driven:** All implementations must pass defined validation gates
- **Self-Correcting:** AI iterates until all quality checks pass
- **Documentation-Rich:** Include relevant external docs and API references

### Context Engineering File Structure:
```
.copilot/
├── prompts/
│   ├── generate-prp.md    # PRP generation for GitHub Copilot Chat
│   └── execute-prp.md     # PRP execution for GitHub Copilot Chat
PRPs/
├── templates/
│   └── prp_base.md       # Base template for all PRPs
└── [feature-prps].md     # Generated implementation blueprints
examples/                  # Critical code patterns and conventions
AGENT_RULES.md            # This file - global rules for AI assistants
```

### Success Metrics:
- Reduced AI failures through comprehensive context
- Consistent implementations following project patterns
- Self-correcting workflows that validate and fix issues
- Complex multi-step features implemented correctly on first try