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
| `GIST_ID` | No | Gist that stores `portfolio.json` for cloud deployments |
| `GITHUB_TOKEN` | No | Fine-grained token, **Gists: read & write only** |
| `MODE` | No | `local` (default) or `cloud`; cloud hides the exit button |
| `APP_PASSWORD` | Cloud: **yes** | Password gate; `MODE = "cloud"` refuses to start without it |

The app runs with zero secrets configured — all features degrade gracefully.

## Deploying (Streamlit Cloud or any public host)

The app has no user accounts. Without `APP_PASSWORD`, anyone with the URL can
edit the portfolio (written to your Gist with your token), send email through
your SMTP account, and spend your Anthropic credits. Before deploying:

1. Set `MODE = "cloud"` and a strong `APP_PASSWORD`.
2. Use a fine-grained GitHub token limited to Gists. A secret Gist is still
   readable by anyone who has its URL — it holds holdings, trades and email
   recipients.

## Data-loss protection

If `portfolio.json`, the Gist, or `trading_journal_ai.json` can't be read, the
app shows a red banner and **blocks saves** for that session instead of
overwriting your data with defaults. A corrupt file is copied to `*.bak` first.

## Setup

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit secrets.toml with your values — never commit it
```

## Email security

- Port 587: STARTTLS (`smtplib.SMTP` + `starttls()`)
- Port 465: SSL/TLS (`smtplib.SMTP_SSL`)
- Use an **app password**, not your account password (Gmail, Outlook, etc.)
- Certificates are verified (`ssl.create_default_context()`), 15s timeout
- Recipient addresses are not written to logs

## What is gitignored

```
.streamlit/secrets.toml   ← secrets
portfolio.json(.bak)      ← personal position data
trading_journal_ai.json   ← personal trade journal
*.docx / *.pdf            ← personal research documents
.env / .env.*             ← any local env files
venv/                     ← virtual environment
```

## Untrusted content

News headlines, Yahoo company descriptions and Claude output are rendered with
`unsafe_allow_html`. They must pass through `esc()` / `safe_url()` from
`src/ui_helpers.py` first; `safe_url()` only allows http(s) links.

**The GitHub repository is public** — check `git status` before every commit.

## Reporting vulnerabilities

Open a private GitHub issue or contact the maintainer directly.
