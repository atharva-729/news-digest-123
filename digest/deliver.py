"""Phase 5: rebuild the archive index in docs/ (served by GitHub Pages), optionally email the edition via
Gmail SMTP, and optionally commit + push so the site updates. Runs locally; no CI and no secrets on GitHub."""
import logging
import os
import re
import smtplib
import ssl
import subprocess
from email.message import EmailMessage

from dotenv import load_dotenv

from digest.common import DATA, ROOT, read_json

log = logging.getLogger(__name__)

SITE = ROOT / "docs"  # GitHub Pages serves this folder from the main branch
SECRETS = ("SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO")


def build_index():
    """docs/index.html: every edition, newest first. Weekly files are named weekly-DATE.html."""
    rows = []
    for p in sorted(SITE.glob("*.html"), key=lambda p: p.stem[-10:], reverse=True):
        if p.name == "index.html":
            continue
        title = re.search(r"<title>(.*?)</title>", p.read_text(encoding="utf-8"), re.S)
        kind = "Weekly" if p.stem.startswith("weekly-") else "Daily"
        rows.append(f'<li style="margin:0 0 6px;"><a href="{p.name}" style="color:#1f2328;">{p.stem[-10:]}</a>'
                    f' <span style="color:#6a737d;font-size:13px;">· {kind}'
                    f'{" · " + title.group(1).split(" · ", 1)[-1] if title and kind == "Weekly" else ""}</span></li>')
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>L1·L2·L3 archive</title></head>
<body style="margin:0;background:#f6f3ee;">
<div style="max-width:640px;margin:0 auto;padding:24px 16px;background:#fffdf9;color:#1f2328;font-family:Georgia,serif;line-height:1.55;">
<h1 style="font-size:26px;margin:0 0 4px;">L1 · L2 · L3 archive</h1>
<p style="margin:0 0 16px;font-style:italic;color:#6a737d;">Headlines tell you what happened. This tells you what it's evidence of.</p>
<ul style="padding-left:18px;">
{chr(10).join(rows)}
</ul>
</div></body></html>
"""
    (SITE / "index.html").write_text(html, encoding="utf-8")
    return len(rows)


def plain_text(html):
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</h[12]>|</div>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def send(subject, html):
    """Returns a short status string. Never logs the secrets."""
    load_dotenv()
    env = {k: os.environ.get(k, "").strip() for k in SECRETS}
    missing = [k for k, v in env.items() if not v]
    if missing:
        return f"skipped (missing {', '.join(missing)})"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, env["SMTP_USER"], env["MAIL_TO"]
    msg.set_content(plain_text(html))
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(env["SMTP_USER"], env["SMTP_APP_PASSWORD"])
        s.send_message(msg)
    return f"sent to {env['MAIL_TO'].split('@')[0][:2]}…@{env['MAIL_TO'].split('@')[-1]}"


def run(cfg, date, weekly=False, no_send=False):
    name = f"weekly-{date}" if weekly else date
    path = SITE / f"{name}.html"
    if not path.exists():
        raise SystemExit(f"no edition at {path}; run the write phase first")
    meta = read_json(DATA / ("weekly" if weekly else "written") / f"{date}.json", {})
    subject = meta.get("subject") or f"L1·L2·L3 {date}"
    count = build_index()
    status = "skipped (--no-send)" if no_send else send(subject, path.read_text(encoding="utf-8"))
    return {"path": path, "subject": subject, "editions": count, "email": status}


def push(date, weekly=False):
    """Commit the run's state and pages, then push. Only data/ and docs/ are staged, never anything else."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    git("add", "data", "docs")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return "nothing new to commit"
    msg = f"{'weekly' if weekly else 'daily'} edition {date}"
    r = git("commit", "-m", msg, "--", "data", "docs")
    if r.returncode != 0:
        return f"commit failed: {r.stderr.strip()[:200]}"
    r = git("push")
    return f"pushed '{msg}'" if r.returncode == 0 else f"committed but push failed: {r.stderr.strip()[:200]}"
