"""Emails the daily breakout scan report as an Excel attachment.

Reads credentials from environment variables (set as GitHub Actions secrets):
    GMAIL_ADDRESS       - the Gmail address to send from
    GMAIL_APP_PASSWORD  - a Gmail App Password (not your normal password)
    RECIPIENT_EMAIL     - who receives the email (defaults to GMAIL_ADDRESS)

Run:
    python send_email.py --pattern "data/output/*.xlsx"
"""

import argparse
import glob
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path


def find_latest_report(pattern):
    matches = sorted(glob.glob(pattern))
    return Path(matches[-1]) if matches else None


def _top_picks_text(attachment):
    """Best-effort plain-text summary of the 'Top Picks' sheet for the email body."""
    try:
        import pandas as pd
        df = pd.read_excel(attachment, sheet_name="Top Picks")
    except Exception:
        return ""
    if df.empty:
        return "No qualifying breakout candidates today (technical + fundamental filters)."
    lines = ["Top Picks (technical + fundamental):", ""]
    for _, r in df.head(10).iterrows():
        rank = r.get("true_rank", "-")
        lines.append(
            f"{rank}. {r.get('symbol', '')} [{r.get('action', '')}] "
            f"close={r.get('close', '-')} score={r.get('final_score', '-')} "
            f"sector={r.get('sector', '-')} PE={r.get('pe_ratio', '-')} ROE={r.get('roe', '-')}"
        )
    return "\n".join(lines)


def _session_label():
    from datetime import datetime, timezone, timedelta
    ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    if ist.hour < 9 or (ist.hour == 9 and ist.minute < 15):
        return "Pre-Market"
    if ist.hour < 15 or (ist.hour == 15 and ist.minute < 30):
        return "Mid-Session"
    return "Post-Close"


def build_message(sender, recipient, attachment):
    msg = EmailMessage()
    status = "report attached" if attachment and attachment.exists() else "no report generated"
    session = _session_label()
    msg["Subject"] = f"Breakout Scanner [{session}] - {status}"
    msg["From"] = sender
    msg["To"] = recipient

    if attachment and attachment.exists():
        top_text = _top_picks_text(attachment)
        body = ((top_text + "\n\n") if top_text else "") + (
            "Full details in the attached Excel report.\n\n"
            "Educational tool only. Not investment advice."
        )
        msg.set_content(body)
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=attachment.name,
        )
    else:
        msg.set_content(
            "No report was generated today.\n\n"
            "Educational tool only. Not investment advice."
        )
    return msg


def main():
    parser = argparse.ArgumentParser(description="Email the breakout scan report")
    parser.add_argument("--pattern", default="data/output/*.xlsx",
                         help="glob pattern to locate the generated report")
    args = parser.parse_args()

    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = os.environ.get("RECIPIENT_EMAIL", sender)

    attachment = find_latest_report(args.pattern)
    msg = build_message(sender, recipient, attachment)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    print(f"Email sent to {recipient}")


if __name__ == "__main__":
    main()
