# Contributing

## Development setup

Footy-Scout supports Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Do not commit `.streamlit/secrets.toml`, cache files or real provider responses
that contain personal or account data. Tests must use synthetic or sanitized
fixtures and must not make live provider requests.

## Before opening a pull request

```bash
python -m ruff check .
python -m mypy app_helpers.py app_state.py fantasy.py scouting.py valuation.py
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python -m compileall -q .
```

Describe the user-visible behavior, data assumptions, API-request impact and
validation performed. Include desktop and mobile evidence for interface changes.
Keep provider retries bounded and disclose stale or unavailable data rather than
silently presenting it as live.
