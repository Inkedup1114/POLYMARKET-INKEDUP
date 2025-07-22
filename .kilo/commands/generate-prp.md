# Kilo Code Command: Generate Product Requirements Prompt (PRP)

## DESCRIPTION
Context Engineering command that reads a feature request file, researches the codebase for comprehensive context and patterns, and generates a detailed Product Requirements Prompt (PRP) with full implementation context.

## USAGE
`/generate-prp <path_to_initial_file>`

## CONTEXT ENGINEERING WORKFLOW
You are a senior technical architect using **Context Engineering** methodology. Your task is to create a comprehensive implementation blueprint for the feature described in `$ARGUMENTS`.

### 1. COMPREHENSIVE CONTEXT ANALYSIS
- **Read Feature Request:** Thoroughly analyze the requirements from `$ARGUMENTS`
- **Project Standards:** Review `AGENT_RULES.md` for ALL project-wide standards and conventions
- **Codebase Patterns:** Analyze existing code in `inkedup_bot/` and `tests/` directories for established patterns
- **Example Patterns:** Study `examples/` directory for architectural patterns and code conventions to follow
- **Documentation Research:** Gather relevant API docs, library guides, and external resources mentioned

### 2. PATTERN IDENTIFICATION & CONTEXT GATHERING
- **Code Architecture:** How similar features are implemented in the existing codebase
- **Testing Patterns:** How tests are structured and what coverage patterns to follow
- **Error Handling:** How the project handles failures, edge cases, and validation
- **Integration Patterns:** How components connect and communicate with each other
- **Documentation Standards:** Docstring format, commenting style, and code documentation

### 3. COMPREHENSIVE BLUEPRINT CREATION
- **Base Template:** Use `PRPs/templates/prp_base.md` as the foundation
- **Complete Context:** Include ALL relevant patterns, examples, documentation, and gotchas
- **Validation Gates:** Define specific tests, quality checks, and validation steps that must pass
- **Error Prevention:** Include common pitfalls, edge cases, and how to avoid implementation failures
- **Success Criteria:** Measurable outcomes and comprehensive checklists for completion

### 4. QUALITY ASSURANCE & COMPLETENESS
- **Context Verification:** Ensure all referenced files, patterns, and documentation exist and are relevant
- **Implementation Completeness:** Verify the plan covers all aspects of the feature request
- **Validation Planning:** Include comprehensive testing strategy with specific test cases
- **Error Handling Coverage:** Plan for failure scenarios and edge case handling
    *   Use the `PRPs/templates/prp_base.md` as the base for the new PRP.
    *   Fill out each section of the template with the information gathered:
        *   **Feature Description:** A clear, concise summary of the goal.
        *   **Context & Docs:** Links to `KILO.md`, relevant existing files, and external documentation.
        *   **Implementation Plan:** A detailed, step-by-step plan for implementation. Each step must be a concrete, actionable task.
        *   **Validation Plan:** Specific instructions on how to test and validate the feature (e.g., unit tests to write, commands to run).
        *   **Success Criteria:** A checklist of conditions that must be met for the task to be considered complete.

4.  **Save PRP:**
    *   Generate a descriptive filename for the PRP based on the feature (e.g., `prp_feature-name.md`).
    *   Save the completed PRP file in the `PRPs/` directory.
    *   Announce the path to the newly created PRP file upon completion.