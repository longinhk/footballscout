# Architecture

## Runtime flow

```text
Browser
  |
  v
Streamlit orchestration (app.py)
  |-- session transitions and search guards (app_state.py)
  |-- local filtering, sharing and favourites (app_helpers.py)
  |-- presentation models and escaped HTML (ui_components.py)
  |
  +--> API-Football adapter (data_fetcher.py)
  |      |-- bounded retry and split timeout
  |      |-- response normalization
  |      `-- atomic, key-free disk cache
  |
  +--> scouting and valuation domain logic
  |      |-- scouting.py
  |      |-- valuation.py
  |      `-- fantasy.py
  |
  `--> in-memory PDF and CSV exports
```

The application intentionally keeps credentials and provider calls on the
server. Browser state contains selected and normalized player data, not the API
key. The fictional catalog provides a deterministic, zero-request path for demos
and provider outages.

## Data and failure policy

1. Validate and normalize user search terms before contacting the provider.
2. Serve a fresh cached response when available.
3. Use bounded retries only for idempotent requests and transient failures.
4. On a temporary outage, use an expired response only when the interface can
   disclose that it is stale.
5. Preserve the final provider requests when the observed quota is low and keep
   the sample catalog available.
6. Preserve missing values as unavailable instead of inventing zeroes.

Cached records are bounded, expire by endpoint-specific policy and exclude the
credential. Writes use a temporary file, restrictive permissions and atomic
replacement. The cache is an availability optimization, not a source of truth.

## Module boundaries

The valuation, scouting and fantasy modules are deterministic domain code and do
not depend on Streamlit. `app_state.py` centralizes transitions that would
otherwise be coupled to widget lifecycle behavior. `data_fetcher.py` owns
provider-specific transport and normalization.

`app.py` and `data_fetcher.py` remain the largest modules. The next safe
decomposition is to extract real-player workflow orchestration, comparison
workflow orchestration, provider transport, cache storage and response parsers
behind typed interfaces. Existing behavior and coverage should be preserved
during that work.

## Quality controls

CI uses Python 3.12, SHA-pinned GitHub Actions and read-only repository
permissions. It runs Ruff, scoped mypy checking, branch-aware coverage with an
84% floor, the complete offline test suite and bytecode compilation. Dependabot
proposes Python and GitHub Actions updates.
