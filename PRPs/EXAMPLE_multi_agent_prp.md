# PRP: Add a CLI Command to Display Bot Version

## 1. Feature Description
Implement a new CLI command `version` that displays the current version of the `inkedup_bot` as defined in `inkedup_bot/version.py`.

---

## 2. Context & Documentation
- **Project Rules:** [`KILO.md`](../KILO.md)
- **Relevant Code:**
  - [`inkedup_bot/cli.py`](../inkedup_bot/cli.py:1) (main Typer app)
  - [`inkedup_bot/version.py`](../inkedup_bot/version.py:1) (source of version string)
- **External Docs:**
  - [Typer - Commands](https://typer.tiangolo.com/tutorial/commands/)

---

## 3. Implementation Plan
1.  **Modify `cli.py`:**
    - Import the `__version__` variable from `inkedup_bot.version`.
    - Create a new function `version()` decorated with `@app.command()`.
    - Inside this function, print the version information to the console (e.g., "Inked-Up Bot Version: 0.1.0").

---

## 4. Validation Plan
1.  **Test Case:**
    - **File:** Create a new test file `tests/test_cli.py`.
    - **Description:** Add a test `test_version_command` that uses Typer's `CliRunner` to invoke the `version` command and assert that the output contains the correct version string from `inkedup_bot.version`.
2.  **Linting:** Run a linter on `inkedup_bot/cli.py` and `tests/test_cli.py` and ensure no errors.
3.  **Manual Check:** Run `python -m inkedup_bot.cli version` from the terminal and verify the output is correct.

---

## 5. Success Criteria
- [ ] `version` command is added to `inkedup_bot/cli.py`.
- [ ] The command correctly prints the version from `inkedup_bot/version.py`.
- [ ] A new test file `tests/test_cli.py` is created with a passing test for the command.
- [ ] All new/modified code is documented and formatted.
- [ ] The `version` command appears in the `--help` output.