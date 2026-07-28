# Footy-Scout

Footy-Scout is a Streamlit workspace for comparing two football players across
season output, per-90 performance and transparent valuation demos.

The app opens with fictional demo players, so the complete comparison and
export flow works without an account or API key. Live comparisons use
[API-Football](https://www.api-football.com/).

## What it includes

- No-key demo mode with four fictional player profiles
- Live API-Football comparisons with cached season responses
- Combined statistics across every competition row returned for a player
- Position-aware, per-90 heuristic and constrained demonstration model
- Explicit equal-weight blended estimate and method spread
- Side-by-side summary, shared performance table and tie handling
- PDF and CSV exports with player-specific filenames
- Actionable API errors and graceful PDF character fallback for unsupported glyphs

> The valuations are educational estimates. They do not include contract data,
> injury history, club finances, league-strength adjustments or verified market
> comparables, and they are not official market values or financial advice.

## Run locally

Python 3.10 or newer is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open <http://localhost:8501>. Demo mode is ready immediately.

### Enable live data

Create `.streamlit/secrets.toml` (already ignored by Git):

```toml
RAPIDAPI_KEY = "your-rapidapi-key"
```

You can alternatively set `RAPIDAPI_KEY` in the environment or enter a
temporary override in the sidebar. A configured server-side key is never sent
back to the password field. Player IDs must be API-Football IDs.

For players returned with several team or competition entries, Footy-Scout sums
counting statistics, uses an appearance-weighted rating, and labels the result
as an all-competitions view.

## Test

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

## Project structure

- `app.py` — Streamlit interface and comparison presentation
- `data_fetcher.py` — API client and response normalization
- `valuation.py` — bounded heuristic and demonstration model
- `pdf_report.py` — in-memory PDF export
- `demo_data.py` — fictional, deterministic demo profiles
- `tests/test_core.py` — parser, model, API and export tests
