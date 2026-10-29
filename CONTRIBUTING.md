# Contributing to NoSteam2Steam

### Project Maintenance Notice
> [!NOTE]
> **NoSteam2Steam is a personal hobby project maintained on an irregular, as-time-permits basis.**
> 
> There is no full-time supervision, active commercial support, or guaranteed response time for issues and pull requests. Features and fixes are developed primarily around the author's own use cases on SteamOS and Linux.
> 
> You are entirely welcome to fork the repository and adapt it to your own workflow under the terms of the license.

---

## Guidelines for Contributions

If you choose to submit a bug fix or improvement, please keep the following practical guidelines in mind so the contribution can be evaluated easily without requiring extensive back-and-forth:

1. **Self-Contained Changes:** Ensure your changes solve a specific issue without introducing regressions in existing workflows.
2. **No Hardcoded Absolute Paths:** Use dynamic path resolution (e.g., `Path.home()`, Steam base directories). Never commit paths specific to your local machine (e.g., `/home/username`).
3. **Preserve UI Decoupling:** Business logic (scanning, backup archiving, shortcut manipulation) should remain separate from interface code. Dialogs should route through `nosteam2steam.ui` rather than direct system calls.
4. **Verify Existing Tests:** Before submitting a pull request, run the test suite to ensure existing functionality remains intact:
   ```bash
   pytest
   ```
   All tests run in headless mode and should pass without requiring an active graphical desktop.

---

## Local Development Quickstart

```bash
# Clone the repository
git clone https://github.com/JesusSolisOrtega/NoSteam2Steam.git
cd NoSteam2Steam

# Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e ".[dev]"

# Run tests and linter
pytest
ruff check nosteam2steam tests
```

---

## Submitting Pull Requests

- Keep descriptions straightforward: explain what was broken, how your change fixes it, and what platform/hardware you tested on (e.g., Steam Deck LCD/OLED, desktop Linux distribution).
- Please understand that review and merge times may vary depending on availability.
