.PHONY: install lint test run-scan

install:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

lint:
	@echo "(Add ruff/flake8 if desired)"

test:
	. .venv/bin/activate && pytest

run-scan:
	. .venv/bin/activate && python -m inkedup_bot.cli scan
