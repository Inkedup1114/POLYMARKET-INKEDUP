# InkedUp Polymarket Bot

**A sophisticated Polymarket trading bot with Agent-Agnostic Context Engineering**

This project implements an advanced trading bot for Polymarket prediction markets with comprehensive context engineering setup for AI-assisted development.

---

## 🚀 Quick Start

### Bot Setup
1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   - Copy `.env.example` to `.env` and configure your Polymarket API credentials
   - Set risk parameters and trading thresholds

3. **Run the bot:**
   ```bash
   # Run scanner once
   python -m inkedup_bot.cli once

   # Start continuous scanning
   python -m inkedup_bot.cli scan --interval 30
   ```

### AI Development Workflow

This project is configured for **Agent-Agnostic Context Engineering** - use it with GitHub Copilot, Kilo Code, or any AI assistant:

1. **Set up your project rules:**
   - Review [`AGENT_RULES.md`](./AGENT_RULES.md) for project-specific guidelines

2. **Use examples:**
   - Check [`examples/`](./examples/) for code patterns and conventions

3. **Create feature requests:**
   - Edit [`INITIAL.md`](./INITIAL.md) with your feature requirements

4. **Generate and execute PRPs:**
   - **For GitHub Copilot:** Use [`.copilot/prompts/generate-prp.md`](./.copilot/prompts/generate-prp.md)
   - **For Kilo Code:** Run `/generate-prp INITIAL.md`

---

## 🏗️ Architecture

### Core Components
- **Scanner**: Market opportunity detection and analysis
- **Strategies**: Pluggable trading strategy implementations
- **Risk Manager**: Position and exposure risk controls
- **Order Client**: Polymarket API integration for order management
- **State Manager**: Portfolio and trade state persistence
- **Database**: SQLite-based data persistence with market snapshots

### Trading Strategies
- **Market Making**: Provides liquidity with bid/ask spreads
- **Spread Arbitrage**: Exploits pricing inefficiencies
- **Custom Strategies**: Extensible strategy framework

---

## 📁 Project Structure

```
polymarket-inkedup/
├── .copilot/prompts/          # GitHub Copilot integration
├── .kilo/commands/            # Kilo Code integration  
├── PRPs/                      # Product Requirements Prompts
│   ├── templates/            
│   └── prp_portfolio_command.md  # Example generated PRP
├── examples/                  # Code pattern examples
│   ├── cli_command_pattern.py
│   └── strategy_pattern.py
├── inkedup_bot/              # Main bot implementation
│   ├── strategies/           # Trading strategy modules
│   └── data/                # Database and data files
├── tests/                    # Unit tests
├── AGENT_RULES.md           # AI assistant guidelines
├── INITIAL.md               # Feature request template
└── README.md               # This file
```

---

## 🔧 Available Tasks

Use VS Code tasks or run directly:

- **Install Dependencies**: `pip install -r requirements.txt`
- **Run Tests**: `python -m pytest tests/ -v`  
- **Format Code**: `python -m black inkedup_bot/ tests/`
- **Lint Code**: `python -m ruff check inkedup_bot/ tests/`
- **Run Scanner Once**: `python -m inkedup_bot.cli once`
- **Start Scanner Loop**: `python -m inkedup_bot.cli scan --interval 30`

---

## 📖 Documentation

- [`TODO.md`](./TODO.md) - Current development status and roadmap
- [`PRPs/EXAMPLE_multi_agent_prp.md`](./PRPs/EXAMPLE_multi_agent_prp.md) - Example PRP workflow
- [`examples/README.md`](./examples/README.md) - Code pattern documentation

---

## 🔒 Security

This project implements comprehensive security measures for safe trading operations:

### Security Features
- **🔐 Secret Management**: Environment-based configuration with secret detection
- **🛡️ API Security**: Rate limiting, authentication, and TLS encryption
- **🔍 Vulnerability Scanning**: Automated dependency and code security scanning
- **📊 Security Monitoring**: Real-time alerts and audit logging
- **🏗️ Secure Deployment**: Non-root containers and infrastructure security

### Quick Security Setup
1. **Copy environment template**: `cp .env.example .env`
2. **Generate secure keys**:
   ```bash
   # Generate JWT secret
   openssl rand -base64 32
   
   # Generate private key (replace with your actual key)
   echo "your_ethereum_private_key_here" > .env
   ```
3. **Run security scans**:
   ```bash
   # Check for secrets
   detect-secrets scan --all-files --baseline .secrets.baseline
   
   # Security audit
   pip-audit --format=json --output=security-report.json
   ```

See [SECURITY.md](./SECURITY.md) for complete security documentation and reporting procedures.

---

## 🤖 AI Development

This project uses **Context Engineering** to maximize AI assistant effectiveness:

### The PRP Workflow
1. **Generate PRP**: Create detailed implementation blueprint from simple feature request
2. **Execute PRP**: AI follows the plan to implement, test, and validate features

### Best Practices
- Use specific, detailed feature requests in `INITIAL.md`
- Reference relevant examples from the `examples/` directory  
- Follow the guidelines in `AGENT_RULES.md`
- Test the PRP workflow with the included example

---

## 🔍 Example: Generated PRP

See [`PRPs/prp_portfolio_command.md`](./PRPs/prp_portfolio_command.md) for a complete example of a generated Product Requirements Prompt that adds a portfolio CLI command.

---

**Ready to build with AI assistance? Edit `INITIAL.md` and generate your first PRP!**
