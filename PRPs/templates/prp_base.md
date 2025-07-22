# PRP: [Feature Name]

## 1. Feature Description
*A clear, comprehensive description of the feature to be implemented, including functional requirements and user experience.*

---

## 2. Context & Documentation  
*Complete context engineering - ALL relevant files, patterns, documentation, and resources.*

- **Project Rules:** [`AGENT_RULES.md`](../../AGENT_RULES.md) - Follow ALL coding standards and conventions
- **Relevant Code Files:**
  - *`path/to/main/file.py` - Brief description of relevance*
  - *`path/to/related/file.py` - What patterns to follow*
- **Code Patterns to Follow:**
  - *`examples/pattern_file.py` - Specific pattern to use (e.g., CLI command structure)*
  - *`examples/architecture_file.py` - Architecture pattern to follow*
- **External Documentation:**
  - *API documentation URLs*
  - *Library documentation links*
  - *MCP server documentation*
- **Gotchas & Common Pitfalls:**
  - *Known issues to avoid*
  - *Edge cases to handle*
  - *Performance considerations*

---

## 3. Implementation Plan
*Detailed, step-by-step implementation with validation checkpoints.*

1.  **[Step Name]:**
    - Specific actions to take
    - Files to modify/create
    - Code patterns to follow from examples
    - Validation: How to verify this step works

2.  **[Next Step]:**
    - Build on previous step
    - Integration with existing components
    - Error handling to implement
    - Validation: Tests to run

3.  **[Final Steps]:**
    - Final integration and cleanup
    - Documentation requirements
    - Final validation steps

---

## 4. Validation Plan
*Comprehensive testing and quality assurance strategy.*

1.  **Unit Tests:**
    - **File:** `tests/test_[component].py`  
    - **Tests to Add:**
      - `test_[feature]_success_case` - Test normal operation
      - `test_[feature]_error_handling` - Test error scenarios
      - `test_[feature]_edge_cases` - Test boundary conditions
    - **Coverage Target:** Aim for >90% coverage of new code

2.  **Integration Tests:**
    - **Manual Testing:** Step-by-step manual verification
    - **System Integration:** How it works with existing components
    - **Performance Testing:** If applicable, performance requirements

3.  **Code Quality:**
    - **Formatting:** Run `black inkedup_bot/ tests/` 
    - **Linting:** Run `ruff check inkedup_bot/ tests/`
    - **Type Checking:** Verify type hints are correct
    - **Documentation:** Ensure docstrings follow Google style

4.  **Error Handling Verification:**
    - Test common failure scenarios
    - Verify graceful degradation
    - Check error messages are helpful

---

## 5. Success Criteria
*Measurable checklist for feature completion - ALL items must be completed.*

### Core Functionality
- [ ] Feature implements ALL requirements from description
- [ ] Follows patterns from referenced example files
- [ ] Integrates properly with existing system components
- [ ] Handles errors gracefully with helpful messages

### Code Quality  
- [ ] All code formatted with Black (no formatting errors)
- [ ] All code passes Ruff linting (no lint errors)
- [ ] Type hints are comprehensive and correct
- [ ] Docstrings follow Google style for all public functions/classes

### Testing
- [ ] Unit tests cover all major functionality (>90% coverage)
- [ ] All unit tests pass without errors
- [ ] Integration testing completed and documented
- [ ] Error handling scenarios are tested

### Documentation & Integration
- [ ] Code follows ALL conventions from AGENT_RULES.md
- [ ] Feature appears in CLI help output (if applicable)
- [ ] Manual testing confirms feature works as expected
- [ ] No regressions in existing functionality

### Validation Gates (All Must Pass)
- [ ] `python -m pytest tests/test_[component].py -v` ✓
- [ ] `black --check inkedup_bot/ tests/` ✓  
- [ ] `ruff check inkedup_bot/ tests/` ✓
- [ ] Manual verification steps completed ✓