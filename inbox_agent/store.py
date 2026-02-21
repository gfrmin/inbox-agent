import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "inbox-agent"


def _emails_path() -> Path:
    return _data_dir() / "emails.jsonl"


def _normalize_email(email: dict) -> dict:
    from_list = email.get("from") or []
    sender = from_list[0].get("email", "unknown") if from_list else "unknown"
    sender_name = from_list[0].get("name", "") if from_list else ""
    return {
        "id": email["id"],
        "from": sender,
        "from_name": sender_name,
        "subject": email.get("subject") or "(no subject)",
        "preview": email.get("preview") or "",
        "received_at": email.get("receivedAt", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def load_emails() -> list[dict]:
    path = _emails_path()
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def load_email_ids() -> set[str]:
    return {e["id"] for e in load_emails()}


def append_emails(emails: list[dict]) -> int:
    path = _emails_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = load_email_ids()
    new = [e for e in emails if e["id"] not in existing_ids]
    with open(path, "a") as f:
        for email in new:
            f.write(json.dumps(_normalize_email(email)) + "\n")
    return len(new)


def emails_path() -> Path:
    return _emails_path()
