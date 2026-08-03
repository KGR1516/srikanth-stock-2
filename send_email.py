"""Emails the daily breakout scan report as an Excel attachment.

Reads credentials from environment variables (set as GitHub Actions secrets):
    GMAIL_ADDRESS       - the Gmail address to send from
    GMAIL_APP_PASSWORD  - a Gmail App Password (not your normal password)
    RECIPIENT_EMAIL     - who receives the email (defaults to GMAIL_ADDRESS)

Run:
    python send_email.py --pattern "breakout-scanner/data/output/*.xlsx"
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


def build_message(sender, recipient, attachment):
    msg = EmailMessage()
    status = "report attached" if attachment and attachment.exists() else "no report generated"
    msg["Subject"] = f"Breakout Scanner - {status}"
    msg["From"] = sender
    msg["To"] = recipient

    if attachment and attachment.exists():
        msg.set_content(
            "Attached is today's breakout scan report.\n\n"
            "Educational tool only. Not investment advice."
        )
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
    parser.add_argument("--pattern", default="breakout-scanner/data/output/*.xlsx",
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
