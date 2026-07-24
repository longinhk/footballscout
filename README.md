# FootballScout

FootballScout is a portfolio-grade Streamlit application for finding and comparing
football players using live API-Football data. It combines interactive performance
visualization, a reproducible regression baseline, grounded explanations, and PDF
reporting.

> The included model is a software-engineering demonstration trained on synthetic
> data. Its output is not an official transfer-market valuation. A credible market
> model requires licensed historical valuation or transfer-fee labels.

## Highlights

- Player search by name with disambiguated API-Football results
- Direct API-Sports authentication and actionable HTTP errors
- One-hour search cache and 15-minute statistics cache
- Side-by-side profiles and an interactive Plotly radar chart
- Scikit-learn preprocessing and Ridge regression pipeline
- Reproducible holdout MAE and R² metrics
- Evidence-based explanation with optional OpenAI Responses API enhancement
- In-memory PDF reports
- Unit tests and GitHub Actions CI
- Streamlit Community Cloud-ready configuration

## Architecture

```text
app.py              Streamlit presentation and session workflow
data_fetcher.py     API client, errors, search, and response normalization
valuation.py        Features, regression pipeline, evaluation, inference
explanations.py     Deterministic and optional LLM explanations
pdf_report.py       In-memory PDF generation
tests/              Offline unit tests
.github/workflows/  Continuous integration
```

The API and model modules do not render Streamlit UI. This separation keeps them
testable and makes a future FastAPI or mobile frontend possible.

## Local setup

```bash
git clone https://github.com/longinhk/footballscout.git
cd footballscout
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Edit `.streamlit/secrets.toml` and add the direct key from the API-Sports dashboard:

```toml
API_SPORTS_KEY = "your-key"
```

Run:

```bash
python -m streamlit run app.py
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests use fixtures and make no paid API calls.

## Optional AI explanation

The deterministic explanation is always available. To enable the LLM enhancement:

```toml
OPENAI_API_KEY = "your-key"
OPENAI_MODEL = "gpt-5.6-luna"
```

The integration uses the Responses API and sends only the displayed structured
statistics and model outputs. If the call fails, the app safely falls back to the
deterministic explanation.

## Deploy on Streamlit Community Cloud

1. Push this repository to GitHub.
2. In Streamlit Community Cloud, create an app from the repository.
3. Set the entry point to `app.py`.
4. Add `API_SPORTS_KEY` under **Advanced settings → Secrets**.
5. Optionally add `OPENAI_API_KEY` and `OPENAI_MODEL`.
6. Deploy, then verify search, comparison, cache behavior, and PDF download.

Never commit `.streamlit/secrets.toml`; it is ignored by Git.

## ML roadmap

The next data-science milestone is replacing synthetic labels with a documented,
licensed dataset containing point-in-time market values or completed transfer fees.
Then:

1. Split chronologically to avoid future-data leakage.
2. Establish naive and linear baselines.
3. Compare tree/boosting models using MAE and calibration by price band.
4. Report performance by position, league, age, and season.
5. Version data, features, model artifact, and evaluation report.

This progression is more credible than presenting a complex model trained on a tiny
or undocumented dataset.
