"""Phase 5: rebuild the archive page in docs/ (served by GitHub Pages), optionally email a teaser that links to
the edition, and optionally commit + push so the site updates. Runs locally; no CI and no secrets on GitHub."""
import logging
import os
import smtplib
import ssl
import subprocess
from datetime import date as Date
from email.message import EmailMessage

from dotenv import load_dotenv

from digest.common import DATA, ROOT, read_json
from digest.write import SITE, env, render

log = logging.getLogger(__name__)

SECRETS = ("SMTP_USER", "SMTP_APP_PASSWORD", "MAIL_TO")


def build_index(cfg):
    """docs/index.html: every edition that has a page, newest first."""
    editions = []
    for p in SITE.glob("*.html"):
        if p.name == "index.html":
            continue
        weekly = p.stem.startswith("weekly-")
        d = p.stem.removeprefix("weekly-")
        meta = read_json(DATA / ("weekly" if weekly else "written") / f"{d}.json", {})
        editions.append({"file": p.name, "date": d, "weekly": weekly, "lead": meta.get("lead", ""),
                         "day": Date.fromisoformat(d).strftime("%d %b").lstrip("0")})
    editions.sort(key=lambda e: (e["date"], not e["weekly"]), reverse=True)  # same day: the daily first
    latest = next((e for e in editions if not e["weekly"]), None)
    render("index.html.j2", SITE / "index.html", editions=editions, latest=latest, credit=cfg["credit"])
    return len(editions)


def send(subject, html, text):
    """Returns a short status string. Never logs the secrets."""
    load_dotenv()
    env_ = {k: os.environ.get(k, "").strip() for k in SECRETS}
    missing = [k for k, v in env_.items() if not v]
    if missing:
        return f"skipped (missing {', '.join(missing)})"
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, env_["SMTP_USER"], env_["MAIL_TO"]
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.login(env_["SMTP_USER"], env_["SMTP_APP_PASSWORD"])
        s.send_message(msg)
    return f"sent to {env_['MAIL_TO'].split('@')[0][:2]}…@{env_['MAIL_TO'].split('@')[-1]}"


def run(cfg, date, weekly=False, no_send=False):
    page = f"{'weekly-' if weekly else ''}{date}.html"
    if not (SITE / page).exists():
        raise SystemExit(f"no edition at {SITE / page}; run the write phase first")
    meta = read_json(DATA / ("weekly" if weekly else "written") / f"{date}.json", {})
    subject = meta.get("subject") or f"L1·L2·L3 {date}"
    count = build_index(cfg)
    status = "skipped (--no-send)"
    if not no_send:
        url = cfg.get("site_url", "").rstrip("/") + "/" + page
        tldr = meta.get("tldr", [])
        html = env().get_template("email.html.j2").render(
            subject=subject, tldr=tldr, hero=meta.get("hero"), url=url, weekly=weekly, credit=cfg["credit"],
            label=("Weekly · " if weekly else "") + Date.fromisoformat(date).strftime("%d %b %Y"))
        text = "\n".join([subject, ""] + [f"{i}. {x['text']}" for i, x in enumerate(tldr, 1)] + ["", url])
        status = send(subject, html, text)
    return {"path": SITE / page, "subject": subject, "editions": count, "email": status}


def push(date, weekly=False):
    """Commit the run's state and pages, then push. Only data/ and docs/ are committed, never anything else."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    git("add", "data", "docs")
    if git("diff", "--cached", "--quiet", "--", "data", "docs").returncode == 0:
        return "nothing new to commit"
    msg = f"{'weekly' if weekly else 'daily'} edition {date}"
    r = git("commit", "-m", msg, "--", "data", "docs")
    if r.returncode != 0:
        return f"commit failed: {r.stderr.strip()[:200]}"
    r = git("push")
    return f"pushed '{msg}'" if r.returncode == 0 else f"committed but push failed: {r.stderr.strip()[:200]}"
