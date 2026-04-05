# Security

## Secrets management

All secrets are stored in `.streamlit/secrets.toml` (gitignored — never committed).
Use `.streamlit/secrets.toml.example` as the setup template.

## Required/optional secrets

| Variable | Required | Purpose |
|---|---|---|
| `FINNHUB_API_KEY` | No | Analyst consensus (falls back to yfinance) |
| `ANTHROPIC_API_KEY` | No | AI daily briefs + 5-filter analysis |
| `SMTP_HOST` | No | Email digest and alerts |
| `SMTP_PORT` | No | 587 = STARTTLS (default), 465 = SSL |
| `SMTP_USER` | No | SMTP sender address |
| `SMTP_PASSWORD` | No | App password — NOT your login password |

The app runs with zero secrets configured — all features degrade gracefully.

## Setup

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your values — never commit it
```

## Email security

- Port 587: STARTTLS (`smtplib.SMTP` + `starttls()`)
- Port 465: SSL/TLS (`smtplib.SMTP_SSL`)
- Use an **app password**, not your account password (Gmail, Outlook, etc.)

## What is gitignored

```
.streamlit/secrets.toml   ← secrets
portfolio.json            ← personal position data
.env / .env.*             ← any local env files
venv/                     ← virtual environment
```

## Reporting vulnerabilities

Open a private GitHub issue or contact the maintainer directly.
