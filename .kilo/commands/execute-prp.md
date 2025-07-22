# Kilo Code Command: Execute Product Requirements Prompt (PRP)

## DESCRIPTION
Context Engineering execution command that implements features using comprehensive context from PRPs, ensuring high-quality, validated implementations through continuous validation and iteration.

## USAGE
`/execute-prp <path_to_prp_file>`

## CONTEXT ENGINEERING EXECUTION WORKFLOW
You are a senior software engineer using **Context Engineering** methodology. Your task is to implement the feature specified in the PRP file at `$ARGUMENTS` with comprehensive validation and quality assurance.

### 1. COMPREHENSIVE CONTEXT LOADING
- **Complete PRP Analysis:** Read and understand the entire PRP file including scope, requirements, and success criteria
- **Context File Review:** Study ALL referenced files, examples, and documentation within the PRP
- **Project Standards:** Review `AGENT_RULES.md` and ensure adherence to ALL project conventions
- **Pattern Study:** Analyze referenced example files to understand which patterns and architectures to follow
- **Validation Understanding:** Comprehend all tests, quality checks, and validation requirements

### 2. IMPLEMENTATION WITH CONTINUOUS VALIDATION
- **Step-by-Step Execution:** Follow the PRP implementation plan exactly, implementing each step with precision
- **Pattern Adherence:** Match coding style, architecture patterns, and conventions from referenced examples
- **Validation Gates:** Run tests, linting, and quality checks after each major implementation milestone
- **Error Handling:** Implement comprehensive error handling as specified in the PRP context
- **Documentation:** Add proper docstrings, comments, and documentation following project standards

### 3. QUALITY ASSURANCE & SELF-CORRECTION
- **Comprehensive Testing:** Execute ALL unit tests, integration tests, and manual verification steps
- **Code Quality:** Apply Black formatting, Ruff linting, and type checking as specified
- **Success Criteria Verification:** Ensure every item in the PRP success criteria checklist is completed
- **Iterative Improvement:** If ANY validation fails, analyze the issue, fix it, and re-validate before proceeding
- **Integration Verification:** Confirm the feature works correctly with existing system components

### 4. COMPLETION VALIDATION & REPORTING
- **All Tests Pass:** Verify unit tests, integration tests, manual checks, and quality gates
- **Pattern Compliance:** Confirm code follows all established patterns from examples and AGENT_RULES.md
- **Documentation Complete:** Ensure proper docstrings, comments, and documentation are in place
- **Success Criteria Met:** Validate that every checklist item from the PRP is completed
- **Summary Report:** Provide comprehensive summary of implementation, files modified, and validation results

## CONTEXT ENGINEERING REQUIREMENTS
Your implementation MUST:
- Follow ALL patterns from referenced example files
- Adhere to conventions specified in AGENT_RULES.md  
- Pass ALL validation gates defined in the PRP
- Meet EVERY item in the success criteria checklist
- Self-correct any failures through iterative improvement
- Provide comprehensive error handling and documentation