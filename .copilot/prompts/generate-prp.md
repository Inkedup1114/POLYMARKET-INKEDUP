# Context Engineering: Generate Product Requirements Prompt (PRP)

## CONTEXT ENGINEERING INSTRUCTIONS
You are a senior technical architect using a **Context Engineering** approach. Your task is to create a comprehensive implementation blueprint (PRP) that includes ALL necessary context for successful feature implementation.

**This is NOT simple prompt engineering** - you must provide complete context including patterns, documentation, validation, and error handling.

**To use this prompt:**
1. Copy this entire file content into GitHub Copilot Chat
2. Replace `[PASTE CONTENT OF INITIAL.md HERE]` with your feature request
3. The AI will generate a comprehensive PRP with full context

---

## CONTEXT ENGINEERING WORKFLOW

### 1. COMPREHENSIVE CONTEXT ANALYSIS
- **Read AGENT_RULES.md:** Review ALL project standards and conventions
- **Analyze Codebase:** Identify existing patterns, architecture, and conventions
- **Study Examples:** Review `examples/` directory for established patterns to follow
- **Research Documentation:** Gather relevant API docs, library guides, and external resources
- **Review Existing PRPs:** Check `PRPs/` directory for similar implementations

### 2. PATTERN IDENTIFICATION
- **Code Patterns:** How similar features are implemented in the codebase
- **Testing Patterns:** How tests are structured and what coverage is expected
- **Error Handling:** How the project handles failures and edge cases
- **Integration Patterns:** How components connect and communicate
- **Documentation Patterns:** Docstring format, commenting style, README structure

### 3. COMPREHENSIVE BLUEPRINT CREATION
- **Use Template:** Start with `PRPs/templates/prp_base.md`
- **Include ALL Context:** Reference patterns, examples, docs, and gotchas
- **Define Validation Gates:** Specific tests and checks that must pass
- **Plan Error Handling:** How to handle common failure scenarios
- **Specify Success Criteria:** Measurable outcomes for completion

### 4. QUALITY ASSURANCE
- **Completeness Check:** Ensure all implementation details are covered
- **Context Verification:** Confirm all referenced files and patterns exist
- **Validation Planning:** Define specific tests and quality checks
- **Error Prevention:** Include common pitfalls and how to avoid them

---

## CONTEXT ENGINEERING REQUIREMENTS

Your generated PRP MUST include:

1. **Complete Context References:**
   - Link to AGENT_RULES.md and relevant sections
   - Reference specific example files and patterns to follow
   - Include relevant API documentation and external resources
   - Mention gotchas and common pitfalls

2. **Detailed Implementation Plan:**
   - Step-by-step instructions with validation checkpoints
   - Specific file modifications with exact function/class names
   - Integration points with existing systems
   - Error handling for each major operation

3. **Comprehensive Validation:**
   - Unit tests with specific test case descriptions
   - Integration tests where applicable
   - Code quality checks (Black, Ruff, type checking)
   - Manual verification steps

4. **Success Criteria Checklist:**
   - Measurable outcomes for each major component
   - Code quality requirements
   - Documentation requirements
   - Testing coverage requirements

---

## FEATURE REQUEST

[PASTE CONTENT OF INITIAL.md HERE]