"""
Daily Email Summary
Searches Gmail for important emails and sends a digest at 16:30 daily.
"""

import os
import base64
import datetime
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

RECIPIENT_EMAIL = os.environ.get("SUMMARY_RECIPIENT", "")
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "20"))


def get_gmail_service():
    creds = None
    token_path = os.environ.get("GMAIL_TOKEN_PATH", "token.json")
    creds_path = os.environ.get("GMAIL_CREDENTIALS_PATH", "credentials.json")

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def search_emails(service, query: str, max_results: int = MAX_RESULTS) -> list[dict]:
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    messages = result.get("messages", [])
    emails = []
    for msg in messages:
        detail = service.users().messages().get(
            userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        emails.append({
            "id": msg["id"],
            "from": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
        })
    return emails


def build_html_summary(
    mentions: list[dict],
    important: list[dict],
    todos: list[dict],
    generated_at: str,
) -> str:
    def email_rows(emails: list[dict]) -> str:
        if not emails:
            return "<tr><td colspan='3' style='color:#888;font-style:italic;padding:6px'>No emails found</td></tr>"
        rows = []
        for e in emails:
            rows.append(
                f"<tr>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{e['from']}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee'>{e['subject']}</td>"
                f"<td style='padding:6px 10px;border-bottom:1px solid #eee;color:#555;font-size:12px'>{e['snippet'][:100]}…</td>"
                f"</tr>"
            )
        return "".join(rows)

    sections = [
        ("🔔 @Mentions", mentions),
        ("⭐ Important / Direct", important),
        ("✅ To-Do Items", todos),
    ]

    blocks = []
    for title, emails in sections:
        count = len(emails)
        blocks.append(f"""
        <h2 style="color:#1a73e8;font-size:16px;margin-top:24px">{title}
            <span style="background:#e8f0fe;color:#1a73e8;border-radius:12px;
                         padding:2px 10px;font-size:13px;margin-left:8px">{count}</span>
        </h2>
        <table width="100%" cellspacing="0" style="border-collapse:collapse;font-size:13px">
            <thead>
                <tr style="background:#f1f3f4">
                    <th style="padding:6px 10px;text-align:left;width:25%">From</th>
                    <th style="padding:6px 10px;text-align:left;width:30%">Subject</th>
                    <th style="padding:6px 10px;text-align:left">Preview</th>
                </tr>
            </thead>
            <tbody>{email_rows(emails)}</tbody>
        </table>
        """)

    total = len(mentions) + len(important) + len(todos)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Google Sans,Roboto,Arial,sans-serif;max-width:800px;
             margin:0 auto;padding:24px;color:#202124">
  <div style="background:#1a73e8;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
    <h1 style="margin:0;font-size:22px">📧 Daily Email Summary</h1>
    <p style="margin:4px 0 0;opacity:.85;font-size:13px">Generated {generated_at} &bull; {total} emails requiring attention</p>
  </div>
  <div style="border:1px solid #e0e0e0;border-top:none;padding:16px 24px;border-radius:0 0 8px 8px">
    {"".join(blocks)}
    <p style="color:#888;font-size:11px;margin-top:32px;border-top:1px solid #f1f3f4;padding-top:12px">
      Sent automatically by daily-email-summary &bull;
      Edit <code>daily_email_summary.py</code> to change search criteria or schedule.
    </p>
  </div>
</body>
</html>"""


def send_summary(service, recipient: str, html: str, subject: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = "me"
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def run():
    service = get_gmail_service()

    today = datetime.date.today().strftime("%Y/%m/%d")
    generated_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # Search queries — adjust to taste
    queries = {
        "mentions": f"to:me OR cc:me subject:(@{RECIPIENT_EMAIL.split('@')[0]}) after:{today}",
        "important": f"to:me is:important after:{today}",
        "todos": f"to:me (\"action required\" OR \"follow up\" OR \"please review\" OR \"TODO\" OR \"to-do\" OR \"FYI\") after:{today}",
    }

    mentions = search_emails(service, queries["mentions"])
    important = search_emails(service, queries["important"])
    todos = search_emails(service, queries["todos"])

    recipient = RECIPIENT_EMAIL or service.users().getProfile(userId="me").execute()["emailAddress"]

    subject = f"📧 Daily Email Summary — {generated_at}"
    html = build_html_summary(mentions, important, todos, generated_at)
    send_summary(service, recipient, html, subject)
    print(f"Summary sent to {recipient}: {len(mentions)} mentions, {len(important)} important, {len(todos)} todos")


if __name__ == "__main__":
    run()
