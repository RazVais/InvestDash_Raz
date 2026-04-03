"""Email reports — compose and send HTML portfolio digests and flag alerts.

SMTP configuration (add to .streamlit/secrets.toml):
    SMTP_HOST     = "smtp.gmail.com"
    SMTP_PORT     = 587              # 587 = STARTTLS  |  465 = SSL
    SMTP_USER     = "you@gmail.com"
    SMTP_PASSWORD = "app-password"   # Gmail: use App Password, not account password
"""

from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import threading
from typing import Optional
from streamlit.runtime.scriptrunner import add_script_run_ctx

from src.logger import get_logger

_log = get_logger(__name__)

# ── Status display helpers ────────────────────────────────────────────────────
_STATUS_ICON  = {"triggered": "🔴", "watch": "🟡", "ok": "🟢", "nodata": "⚫"}
_STATUS_COLOR = {
    "triggered": "#f44336",
    "watch":     "#ff9800",
    "ok":        "#4caf50",
    "nodata":    "#555555",
}
_STATUS_LABEL = {"triggered": "מופעל", "watch": "מעקב", "ok": "תקין", "nodata": "אין נתונים"}


# ── HTML builder ─────────────────────────────────────────────────────────────

def _base_style():
    return """
    body{font-family:Arial,Helvetica,sans-serif;background:#0e1117;color:#e0e0e0;
         direction:rtl;margin:0;padding:0}
    .wrap{max-width:680px;margin:0 auto;padding:16px}
    .hdr{background:#00cf8d;color:#000;padding:20px 24px;border-radius:8px 8px 0 0;text-align:center}
    .hdr h2{margin:0;font-size:22px}
    .hdr p{margin:4px 0 0;font-size:13px;opacity:.8}
    .card{background:#1a1f2e;border-radius:8px;padding:16px 20px;margin:12px 0}
    .card h3{margin:0 0 12px;font-size:15px;color:#00cf8d}
    table{width:100%;border-collapse:collapse}
    th{text-align:right;padding:6px 8px;color:#00cf8d;font-size:11px;
       border-bottom:1px solid #333}
    td{padding:6px 8px;font-size:12px;border-bottom:1px solid #1f2937;
       vertical-align:top}
    .pos{color:#4caf50} .neg{color:#f44336} .warn{color:#ff9800}
    .dim{color:#888} .bold{font-weight:700}
    .news-item{padding:6px 0;border-bottom:1px solid #1f2937}
    .news-item a{color:#64b5f6;text-decoration:none;font-size:13px}
    .footer{text-align:center;color:#555;font-size:11px;margin-top:20px}
    """


def build_digest_html(portfolio, data, flag_statuses, td_str):
    """Build full Hebrew HTML digest email body."""
    from src.data.prices import lookup_buy_price
    from src.portfolio import all_tickers, lots_for_ticker

    prices     = data.get("prices", {})
    news_data  = data.get("news", {})

    # ── P&L totals ─────────────────────────────────────────────────────────
    total_cost = total_value = 0.0
    for t in all_tickers(portfolio):
        p = prices.get(t)
        if not p:
            continue
        for _layer, lot in lots_for_ticker(portfolio, t):
            shares = lot.get("shares", 0)
            if shares <= 0:
                continue
            bp = lookup_buy_price(t, lot["buy_date"], prices)
            if bp:
                total_cost  += shares * bp
                total_value += shares * p["price"]

    pnl     = total_value - total_cost
    pnl_pct = (pnl / total_cost * 100) if total_cost > 0 else 0.0
    pnl_cls = "pos" if pnl >= 0 else "neg"

    # ── Flag rows (only non-ok) ─────────────────────────────────────────────
    flag_rows = ""
    triggered_count = watch_count = 0
    for f in flag_statuses:
        if f["status"] == "ok":
            continue
        if f["status"] == "triggered":
            triggered_count += 1
        elif f["status"] == "watch":
            watch_count += 1
        icon  = _STATUS_ICON.get(f["status"], "")
        color = _STATUS_COLOR.get(f["status"], "#888")
        label = _STATUS_LABEL.get(f["status"], f["status"])
        detail_span = (
            f'<br><span class="dim" style="font-size:10px">{f["detail"]}</span>'
            if f.get("detail") else ""
        )
        flag_rows += (
            f'<tr>'
            f'<td style="color:{color}">{icon} {label}</td>'
            f'<td class="bold" style="color:{color}">{f["ticker"]}</td>'
            f'<td>{f["flag"]}</td>'
            f'<td class="dim">{f["threshold"]}</td>'
            f'<td>{detail_span}</td>'
            f'</tr>'
        )

    if not flag_rows:
        flag_section = '<p style="color:#4caf50">🟢 כל הדגלים תקינים</p>'
    else:
        flag_section = f"""
        <table>
          <thead><tr>
            <th>סטטוס</th><th>Ticker</th><th>דגל</th><th>סף</th><th>פרטים</th>
          </tr></thead>
          <tbody>{flag_rows}</tbody>
        </table>"""

    # ── News section (top 2 articles per ticker) ───────────────────────────
    news_html = ""
    for t in sorted(all_tickers(portfolio)):
        articles = news_data.get(t, [])[:2]
        if not articles:
            continue
        news_html += f'<p class="bold" style="color:#00cf8d;margin:12px 0 4px">{t}</p>'
        for art in articles:
            pub  = art.get("published")
            date_str = pub.strftime("%d.%m.%Y") if pub else ""
            news_html += (
                f'<div class="news-item">'
                f'<a href="{art.get("link","#")}" target="_blank">{art.get("title","")}</a>'
                f'<br><span class="dim">{art.get("publisher","")} · {date_str}</span>'
                f'</div>'
            )
    if not news_html:
        news_html = '<p class="dim">אין חדשות זמינות.</p>'

    flag_summary_line = (
        f'<span style="color:#f44336">🔴 {triggered_count} מופעל</span> &nbsp;'
        f'<span style="color:#ff9800">🟡 {watch_count} מעקב</span>'
        if (triggered_count or watch_count)
        else '<span style="color:#4caf50">🟢 הכל תקין</span>'
    )

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><style>{_base_style()}</style></head>
<body>
<div class="wrap">
  <div class="hdr">
    <h2>📊 RazDashboard — דוח תיק יומי</h2>
    <p>{td_str}</p>
  </div>

  <div class="card">
    <h3>💼 סיכום תיק</h3>
    <table>
      <tr><td class="dim">שווי נוכחי</td>
          <td class="bold">${total_value:,.0f}</td></tr>
      <tr><td class="dim">עלות כוללת</td>
          <td>${total_cost:,.0f}</td></tr>
      <tr><td class="dim">רווח / הפסד</td>
          <td class="bold {pnl_cls}">${pnl:+,.0f} ({pnl_pct:+.1f}%)</td></tr>
    </table>
  </div>

  <div class="card">
    <h3>🚩 דגלים אדומים &nbsp; {flag_summary_line}</h3>
    {flag_section}
  </div>

  <div class="card">
    <h3>📰 חדשות עיקריות</h3>
    {news_html}
  </div>

  <div class="footer">
    נשלח אוטומטית מ-RazDashboard · {date.today().strftime("%d/%m/%Y")}
  </div>
</div>
</body>
</html>"""
    return html


def build_alert_html(triggered_flags, td_str):
    """Build a short HTML alert for newly-triggered red flags."""
    rows = ""
    for f in triggered_flags:
        rows += (
            f'<tr>'
            f'<td class="bold" style="color:#f44336">{f["ticker"]}</td>'
            f'<td>{f["flag"]}</td>'
            f'<td class="dim">{f.get("detail","")}</td>'
            f'<td class="dim">{f["action"]}</td>'
            f'</tr>'
        )
    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head><meta charset="UTF-8"><style>{_base_style()}</style></head>
<body>
<div class="wrap">
  <div class="hdr" style="background:#f44336;color:#fff">
    <h2>🔴 RazDashboard — התרעת דגל חדש</h2>
    <p>{td_str}</p>
  </div>
  <div class="card">
    <h3>דגלים חדשים שהופעלו</h3>
    <table>
      <thead><tr>
        <th>Ticker</th><th>דגל</th><th>פרטים</th><th>פעולה מומלצת</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <div class="footer">RazDashboard · {date.today().strftime("%d/%m/%Y")}</div>
</div>
</body>
</html>"""
    return html


# ── SMTP sender ───────────────────────────────────────────────────────────────

def _smtp_send(recipients, subject, html_body, smtp_cfg):
    """Low-level blocking SMTP send. Call from a thread."""
    host = smtp_cfg.get("host", "")
    port = int(smtp_cfg.get("port", 587))
    user = smtp_cfg.get("user", "")
    pwd  = smtp_cfg.get("password", "")
    if not (host and user and pwd):
        _log.warning("SMTP not configured — skip send")
        return False

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"RazDashboard <{user}>"
    msg["To"]       = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as s:
                s.login(user, pwd)
                s.sendmail(user, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as s:
                s.ehlo()
                s.starttls()
                s.login(user, pwd)
                s.sendmail(user, recipients, msg.as_string())
        _log.info("Email sent", extra={"to": recipients, "subject": subject})
        return True
    except Exception:
        _log.error("Email send failed", exc_info=True, extra={"host": host, "to": recipients})
        return False


def send_digest_async(
    portfolio,
    data,
    flag_statuses: list,
    td_str: str,
    recipients: list,
    smtp_cfg: dict,
    on_done=None,
):
    """Build and send the daily digest in a daemon thread (non-blocking)."""
    def _run():
        html    = build_digest_html(portfolio, data, flag_statuses, td_str)
        subject = f"📊 RazDashboard — דוח תיק {td_str}"
        ok      = _smtp_send(recipients, subject, html, smtp_cfg)
        if on_done:
            on_done(ok)

    t = threading.Thread(target=_run, daemon=True)
    add_script_run_ctx(t)
    t.start()


def send_alert_async(
    triggered_flags: list,
    td_str: str,
    recipients: list,
    smtp_cfg: dict,
    on_done=None,
):
    """Build and send a flag-alert email in a daemon thread (non-blocking)."""
    def _run():
        tickers = ", ".join(f["ticker"] for f in triggered_flags)
        html    = build_alert_html(triggered_flags, td_str)
        subject = f"🔴 RazDashboard — התרעה: {tickers}"
        ok      = _smtp_send(recipients, subject, html, smtp_cfg)
        if on_done:
            on_done(ok)

    t = threading.Thread(target=_run, daemon=True)
    add_script_run_ctx(t)
    t.start()


def send_digest_sync(portfolio, data, flag_statuses, td_str, recipients, smtp_cfg):
    """Synchronous send for immediate UI feedback."""
    html    = build_digest_html(portfolio, data, flag_statuses, td_str)
    subject = f"📊 RazDashboard — דוח תיק {td_str}"
    return _smtp_send(recipients, subject, html, smtp_cfg)


def smtp_configured(smtp_cfg: dict) -> bool:
    """Return True if all required SMTP fields are present."""
    return bool(smtp_cfg.get("host") and smtp_cfg.get("user") and smtp_cfg.get("password"))


def test_smtp(smtp_cfg: dict, recipient: str) -> Optional[str]:
    """Blocking test send. Returns None on success, error string on failure."""
    html    = "<p>RazDashboard SMTP test — success ✅</p>"
    subject = "RazDashboard — SMTP Test"
    ok = _smtp_send([recipient], subject, html, smtp_cfg)
    return None if ok else "שליחה נכשלה — בדוק SMTP_HOST, SMTP_USER, SMTP_PASSWORD"
