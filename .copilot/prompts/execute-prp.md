# Context Engineering: Execute Product Requirements Prompt (PRP)

## CONTEXT ENGINEERING INSTRUCTIONS
You are a senior software engineer using a **Context Engineering** approach. Your task is to implement features using comprehensive context from the PRP, ensuring high-quality, validated implementations.

**This is NOT simple code generation** - you must follow all patterns, validate continuously, and iterate until success criteria are met.

**To use this prompt:**
1. Copy this entire file content into GitHub Copilot Chat  
2. Replace `[PASTE CONTENT OF THE PRP FILE HERE]` with the complete PRP content
3. The AI will implement the feature with continuous validation

---

## CONTEXT ENGINEERING EXECUTION WORKFLOW

### 1. COMPREHENSIVE CONTEXT LOADING
- **Read Complete PRP:** Understand scope, requirements, and success criteria
- **Review Referenced Files:** Study all linked code, examples, and documentation  
- **Load Project Context:** Review AGENT_RULES.md and project conventions
- **Pattern Analysis:** Identify which examples and patterns to follow
- **Validation Planning:** Understand all tests and quality checks required

### 2. IMPLEMENTATION WITH CONTINUOUS VALIDATION
- **Step-by-Step Execution:** Follow PRP implementation plan exactly
- **Pattern Adherence:** Match coding style and architecture from examples
- **Validation Gates:** Run tests after each major implementation step
- **Error Handling:** Implement proper error handling as specified
- **Documentation:** Add docstrings and comments following project standards

### 3. QUALITY ASSURANCE & ITERATION
- **Test Execution:** Run all unit tests and integration tests
- **Code Quality:** Apply Black formatting and Ruff linting
- **Success Criteria Check:** Verify all PRP success criteria are met
- **Fix Iterations:** If validation fails, analyze and fix issues
- **Final Verification:** Ensure complete, working implementation

### 4. COMPLETION VERIFICATION
- **All Tests Pass:** Unit tests, integration tests, and manual checks
- **Code Quality:** Formatted, linted, and documented properly
- **Success Criteria:** Every checklist item from PRP is completed
- **Integration:** Feature works with existing system components

---

## CONTEXT ENGINEERING REQUIREMENTS

Your implementation MUST:

1. **Follow All Context:**
   - Adhere to patterns from referenced example files
   - Follow conventions from AGENT_RULES.md
   - Match existing code style and architecture
   - Handle errors as specified in the PRP

2. **Validate Continuously:**
   - Run tests after each major step
   - Fix any test failures before proceeding
   - Apply code formatting and linting
   - Verify integration with existing components

3. **Meet All Success Criteria:**
   - Complete every item in the PRP success criteria checklist
   - Ensure proper documentation (docstrings, comments)
   - Verify manual testing steps if specified
   - Confirm feature works as described

4. **Self-Correct When Needed:**
   - If tests fail, analyze the issue and fix it
   - If code quality checks fail, address the problems
   - If integration breaks, debug and resolve
   - Continue iterating until all validations pass

---

## PRP CONTENT

[PASTE CONTENT OF THE PRP FILE HERE]