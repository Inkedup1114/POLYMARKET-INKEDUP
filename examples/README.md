# Context Engineering Code Examples

This directory contains curated code examples that demonstrate preferred patterns, architecture, and conventions for this project. These examples are **critical** for Context Engineering - AI assistants perform much better when they can see patterns to follow.

## Context Engineering Purpose

The `examples/` directory is a core component of our Context Engineering system:
- **Pattern Recognition:** AI can identify and follow established conventions
- **Quality Consistency:** Ensures all new code matches project standards  
- **Error Reduction:** Reduces implementation failures by providing clear templates
- **Architecture Guidance:** Shows how components should interact

## When to Reference Examples

- **In INITIAL.md:** Reference specific examples to guide implementation
- **In PRPs:** Include example patterns in implementation plans
- **During Code Review:** Verify new code follows established patterns

## Current Examples:

### CLI Patterns
- **`cli_command_pattern.py`**: Complete pattern for adding new CLI commands using Typer framework
  - Async operation handling
  - Configuration loading patterns
  - Parameter validation and type hints
  - Error handling and user feedback
  - Rich console formatting

### Architecture Patterns  
- **`strategy_pattern.py`**: Base class inheritance for trading strategies
  - Abstract base class implementation
  - Market data evaluation patterns
  - Action generation and validation
  - Risk management integration

## Example Structure Guidelines

Each example should include:
- **Clear Documentation:** What pattern it demonstrates
- **Complete Implementation:** Fully working, not just snippets
- **Error Handling:** How to handle common failure cases
- **Testing Patterns:** How the code should be tested
- **Integration Points:** How it connects to other system components

## Adding New Examples

When adding examples:
1. Follow the established naming convention
2. Include comprehensive docstrings
3. Add entry to this README
4. Ensure code is formatted with Black
5. Include error handling patterns