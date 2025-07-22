#  Engineering ContextGuide for InkedUp Bot

This document explains the **Context Engineering** system used in this project for working with GitHub Copilot Chat and Kilo Code extensions.

## Context Engineering vs Prompt Engineering

**Prompt Engineering:** Focuses on clever wording and specific phrasing (like giving someone a sticky note)

**Context Engineering:** A complete system providing comprehensive context including:
- Documentation and examples  
- Rules and patterns
- Validation loops
- Error handling strategies
- Architecture guidance

## Why Context Engineering Matters

- **Reduces AI Failures:** Most agent failures aren't model failures - they're context failures
- **Ensures Consistency:** AI follows your project patterns and conventions  
- **Enables Complex Features:** AI can handle multi-step implementations with proper context
- **Self-Correcting:** Validation loops allow AI to fix its own mistakes

## Context Engineering File Structure

```
/home/ink/polymarket-inkedup/
├── .copilot/
│   └── prompts/
│       ├── generate-prp.md    # PRP generation for GitHub Copilot Chat
│       └── execute-prp.md     # PRP execution for GitHub Copilot Chat
├── PRPs/
│   ├── templates/
│   │   └── prp_base.md       # Base template for all PRPs
│   └── [feature-prps].md     # Generated implementation blueprints
├── examples/                  # Critical code patterns and conventions
│   ├── README.md             # Explains what each example demonstrates
│   ├── cli_command_pattern.py # CLI implementation patterns
│   └── strategy_pattern.py   # Strategy architecture patterns
├── AGENT_RULES.md            # Global rules for AI assistants (Context Engineering core)
├── CONTEXT_ENGINEERING.md   # This guide
├── INITIAL.md               # Template for feature requests
└── INITIAL_EXAMPLE.md       # Example feature request
```

## Step-by-Step Context Engineering Workflow

### 1. Create Feature Request (INITIAL.md)

Edit `INITIAL.md` to describe what you want to build:

```markdown
## FEATURE:
[Describe what you want to build - be specific about functionality and requirements]

## EXAMPLES:
[List example files in examples/ folder and explain how they should be used]

## DOCUMENTATION:
[Include links to relevant documentation, APIs, or resources]

## OTHER CONSIDERATIONS:
[Mention gotchas, specific requirements, or things AI commonly misses]
```

### 2. Generate PRP (Product Requirements Prompt)

**For GitHub Copilot Chat:**
1. Copy the entire content of `.copilot/prompts/generate-prp.md`
2. Paste it into GitHub Copilot Chat
3. Replace `[PASTE CONTENT OF INITIAL.md HERE]` with your `INITIAL.md` content

**For Kilo Code Extension:**
```
/generate-prp INITIAL.md
```

This creates a comprehensive PRP in `PRPs/your-feature-name.md` including:
- Complete context and documentation
- Implementation steps with validation  
- Error handling patterns
- Test requirements

### 3. Execute the PRP

**For GitHub Copilot Chat:**
1. Copy the entire content of `.copilot/prompts/execute-prp.md`
2. Paste it into GitHub Copilot Chat  
3. Replace `[PASTE CONTENT OF THE PRP FILE HERE]` with the generated PRP content

**For Kilo Code Extension:**
```
/execute-prp PRPs/your-feature-name.md
```

The AI will:
- Read all context from the PRP
- Create detailed implementation plan
- Execute each step with validation
- Run tests and fix any issues
- Ensure all success criteria are met

## Writing Effective Feature Requests

### Key Sections Explained

**FEATURE:** Be specific and comprehensive
- ❌ "Build a web scraper"
- ✅ "Build an async web scraper using BeautifulSoup that extracts product data from e-commerce sites, handles rate limiting, and stores results in PostgreSQL"

**EXAMPLES:** Leverage the examples/ folder
- Place relevant code patterns in `examples/`
- Reference specific files and patterns to follow
- Explain what aspects should be mimicked

**DOCUMENTATION:** Include all relevant resources
- API documentation URLs
- Library guides  
- Database schemas
- Authentication patterns

**OTHER CONSIDERATIONS:** Capture important details
- Authentication requirements
- Rate limits or quotas
- Common pitfalls
- Performance requirements

## The PRP (Product Requirements Prompt) System

### How Generate-PRP Works
1. **Research Phase:** Analyzes your codebase for patterns
2. **Documentation Gathering:** Fetches relevant API docs and includes gotchas
3. **Blueprint Creation:** Creates step-by-step implementation plan with validation gates
4. **Quality Check:** Ensures all context is included

### How Execute-PRP Works  
1. **Load Context:** Reads the entire PRP
2. **Plan:** Creates detailed task list
3. **Execute:** Implements each component with continuous validation
4. **Validate:** Runs tests and linting after each step
5. **Iterate:** Fixes any issues found
6. **Complete:** Ensures all requirements met

## Using Examples Effectively

The `examples/` folder is critical for success. AI coding assistants perform much better when they can see patterns to follow.

### What to Include in Examples

**Code Structure Patterns:**
- How you organize modules
- Import conventions  
- Class/function patterns

**Testing Patterns:**
- Test file structure
- Mocking approaches
- Assertion styles

**Integration Patterns:**
- API client implementations
- Database connections
- Authentication flows

**CLI Patterns:**
- Argument parsing
- Output formatting
- Error handling

## Best Practices

### 1. Be Explicit in Feature Requests
- Don't assume the AI knows your preferences
- Include specific requirements and constraints
- Reference examples liberally

### 2. Provide Comprehensive Examples
- More examples = better implementations
- Show both what to do AND what not to do
- Include error handling patterns

### 3. Use Validation Gates
- PRPs include test commands that must pass
- AI will iterate until all validations succeed  
- This ensures working code on first try

### 4. Leverage Documentation
- Include official API docs
- Add library guides and patterns
- Reference specific documentation sections

### 5. Customize AGENT_RULES.md
- Add your specific conventions
- Include project-specific rules
- Define coding standards clearly

## Context Engineering Success Metrics

- **Reduced Failures:** Features work correctly on first implementation
- **Consistent Quality:** All code follows established patterns
- **Self-Correction:** AI fixes issues through validation loops
- **Complex Features:** Multi-step implementations succeed without manual intervention

## Troubleshooting

### Common Issues

**"AI doesn't follow my patterns"**
- Add more examples to `examples/` directory
- Reference specific patterns in feature requests
- Update `AGENT_RULES.md` with clearer guidelines

**"Generated code has bugs"**
- Ensure PRPs include comprehensive validation steps
- Add error handling patterns to examples
- Include edge case testing in validation plans

**"AI misses requirements"**
- Be more specific in feature descriptions
- Include all context in INITIAL.md
- Reference relevant documentation explicitly

### Getting Help

1. Check existing PRPs in `PRPs/` directory for similar implementations
2. Review `examples/` directory for relevant patterns
3. Ensure `AGENT_RULES.md` covers your specific requirements
4. Add missing patterns to `examples/` directory

## Examples of Context Engineering in Action

See these files for complete examples:
- `PRPs/prp_portfolio_command.md` - Complete PRP example
- `INITIAL_EXAMPLE.md` - Example feature request
- `examples/cli_command_pattern.py` - CLI implementation pattern

This Context Engineering system ensures consistent, high-quality implementations that follow your project's patterns and conventions.
