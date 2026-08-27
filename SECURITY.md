# Security policy

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Report a
vulnerability** flow when it is available. If private reporting is unavailable,
contact the repository owner without including credentials, exploit details or
personal data in a public issue.

Include the affected revision, impact, reproduction steps and any suggested
mitigation. You should receive an acknowledgement within seven days. Please
allow time for a fix before public disclosure.

## Credential handling

Footy-Scout uses a server-side API-Football or legacy RapidAPI key. Visitors are
never asked to enter a key. Local credentials belong in
`.streamlit/secrets.toml`, which is excluded from Git. Hosted credentials belong
in the deployment platform's secret store.

The key is sent only in the provider request header. It is excluded from cache
keys and cached payloads, redacted from provider errors, and must never be
logged, committed, embedded in screenshots or pasted into issues. Rotate the
credential immediately if exposure is suspected.

## Scope

Automated tests cover key redaction, cache behavior and provider error handling,
but they are not a penetration test or complete secret-history audit. Dependency
updates are proposed automatically and should be reviewed with the full CI suite.
