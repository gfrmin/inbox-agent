import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _data_dir() -> Path:
    base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(base) / "inbox-agent"


def _db_path() -> Path:
    return _data_dir() / "inbox.db"


def _jsonl_path() -> Path:
    return _data_dir() / "emails.jsonl"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA = """\
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,
    sender TEXT,
    sender_name TEXT,
    subject TEXT,
    preview TEXT,
    received_at TEXT,
    fetched_at TEXT,
    processed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id TEXT REFERENCES emails(id),
    evidence_type TEXT,
    content TEXT,
    topic TEXT,
    confidence REAL,
    extracted_at TEXT
);

CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT,
    answer TEXT,
    email_ids TEXT,
    topics TEXT,
    asked_at TEXT
);
"""


def init_db() -> sqlite3.Connection:
    conn = _connect()
    conn.executescript(_SCHEMA)
    _migrate_jsonl(conn)
    return conn


def _migrate_jsonl(conn: sqlite3.Connection) -> None:
    jsonl = _jsonl_path()
    if not jsonl.exists():
        return
    lines = jsonl.read_text().splitlines()
    emails = [json.loads(line) for line in lines if line.strip()]
    if not emails:
        jsonl.rename(jsonl.with_suffix(".jsonl.migrated"))
        return
    conn.executemany(
        """INSERT OR IGNORE INTO emails
           (id, sender, sender_name, subject, preview, received_at, fetched_at)
           VALUES (:id, :sender, :sender_name, :subject, :preview, :received_at, :fetched_at)""",
        [
            {
                "id": e["id"],
                "sender": e.get("from", "unknown"),
                "sender_name": e.get("from_name", ""),
                "subject": e.get("subject", "(no subject)"),
                "preview": e.get("preview", ""),
                "received_at": e.get("received_at", ""),
                "fetched_at": e.get("fetched_at", ""),
            }
            for e in emails
        ],
    )
    conn.commit()
    jsonl.rename(jsonl.with_suffix(".jsonl.migrated"))


def _normalize_email(email: dict) -> dict:
    from_list = email.get("from") or []
    sender = from_list[0].get("email", "unknown") if from_list else "unknown"
    sender_name = from_list[0].get("name", "") if from_list else ""
    return {
        "id": email["id"],
        "sender": sender,
        "sender_name": sender_name,
        "subject": email.get("subject") or "(no subject)",
        "preview": email.get("preview") or "",
        "received_at": email.get("receivedAt", ""),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def append_emails(emails: list[dict]) -> int:
    conn = init_db()
    normalized = [_normalize_email(e) for e in emails]
    cursor = conn.executemany(
        """INSERT OR IGNORE INTO emails
           (id, sender, sender_name, subject, preview, received_at, fetched_at)
           VALUES (:id, :sender, :sender_name, :subject, :preview, :received_at, :fetched_at)""",
        normalized,
    )
    conn.commit()
    conn.close()
    return cursor.rowcount


def email_count() -> int:
    conn = init_db()
    count = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    conn.close()
    return count


def search_emails(query: str | None = None, days: int | None = None, limit: int = 30) -> list[dict]:
    conn = init_db()
    clauses, params = [], []

    if query:
        clauses.append("(subject LIKE ? OR preview LIKE ? OR sender LIKE ? OR sender_name LIKE ?)")
        pattern = f"%{query}%"
        params.extend([pattern] * 4)

    if days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        clauses.append("received_at >= ?")
        params.append(cutoff_iso)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM emails {where} ORDER BY received_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unprocessed() -> list[dict]:
    conn = init_db()
    rows = conn.execute(
        "SELECT * FROM emails WHERE processed = 0 ORDER BY received_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_processed(email_id: str) -> None:
    conn = init_db()
    conn.execute("UPDATE emails SET processed = 1 WHERE id = ?", (email_id,))
    conn.commit()
    conn.close()


def append_evidence(facts: list[dict]) -> int:
    if not facts:
        return 0
    conn = init_db()
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        """INSERT INTO evidence (email_id, evidence_type, content, topic, confidence, extracted_at)
           VALUES (:email_id, :evidence_type, :content, :topic, :confidence, :extracted_at)""",
        [{**f, "extracted_at": now} for f in facts],
    )
    conn.commit()
    count = len(facts)
    conn.close()
    return count


def search_evidence(query: str, limit: int = 30) -> list[dict]:
    conn = init_db()
    rows = conn.execute(
        """SELECT * FROM evidence
           WHERE content LIKE ? OR topic LIKE ?
           ORDER BY extracted_at DESC LIMIT ?""",
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_query(question: str, answer: str, email_ids: list[str], topics: list[str]) -> None:
    conn = init_db()
    conn.execute(
        """INSERT INTO queries (question, answer, email_ids, topics, asked_at)
           VALUES (?, ?, ?, ?, ?)""",
        (question, answer, json.dumps(email_ids), json.dumps(topics), datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def search_queries(query: str | None = None, limit: int = 10) -> list[dict]:
    conn = init_db()
    if query:
        rows = conn.execute(
            """SELECT * FROM queries
               WHERE question LIKE ? OR answer LIKE ? OR topics LIKE ?
               ORDER BY asked_at DESC LIMIT ?""",
            (f"%{query}%", f"%{query}%", f"%{query}%", limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM queries ORDER BY asked_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_topic_weights() -> list[tuple[str, int]]:
    conn = init_db()
    evidence_topics = conn.execute(
        "SELECT topic, COUNT(*) as cnt FROM evidence WHERE topic IS NOT NULL GROUP BY topic"
    ).fetchall()
    query_rows = conn.execute("SELECT topics FROM queries WHERE topics IS NOT NULL").fetchall()
    conn.close()

    counts: dict[str, int] = {}
    for row in evidence_topics:
        counts[row["topic"]] = row["cnt"]
    for row in query_rows:
        for topic in json.loads(row["topics"] or "[]"):
            counts[topic] = counts.get(topic, 0) + 1

    return sorted(counts.items(), key=lambda x: x[1], reverse=True)


_STOP_WORDS = frozenset(
    "i me my we our you your he she it they them their a an the and but or "
    "if in on at to for of is am are was were be been being have has had do "
    "does did will would shall should can could may might must about from with "
    "this that these those what which who whom how when where why all any each "
    "some no not so than too very just also there here then now".split()
)


def _extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from a natural language query."""
    words = [w.strip("?.,!\"'()[]{}") for w in text.lower().split()]
    keywords = [w for w in words if w and w not in _STOP_WORDS and len(w) > 2]
    return keywords or [text]


def search(query: str, days: int | None = None, limit: int = 30) -> dict:
    keywords = _extract_keywords(query)

    seen_email_ids: set[str] = set()
    emails: list[dict] = []
    seen_evidence_ids: set[int] = set()
    evidence: list[dict] = []

    for kw in keywords:
        for e in search_emails(query=kw, days=days, limit=limit):
            if e["id"] not in seen_email_ids:
                seen_email_ids.add(e["id"])
                emails.append(e)
        for ev in search_evidence(kw, limit=limit):
            if ev["id"] not in seen_evidence_ids:
                seen_evidence_ids.add(ev["id"])
                evidence.append(ev)

    past_queries = search_queries(query, limit=10)
    return {
        "emails": emails[:limit],
        "evidence": evidence[:limit],
        "queries": past_queries,
    }


def db_path() -> Path:
    return _db_path()


def status() -> dict:
    conn = init_db()
    total = conn.execute("SELECT COUNT(*) FROM emails").fetchone()[0]
    processed = conn.execute("SELECT COUNT(*) FROM emails WHERE processed = 1").fetchone()[0]
    facts = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    query_count = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    topic_count = conn.execute(
        "SELECT COUNT(DISTINCT topic) FROM evidence WHERE topic IS NOT NULL"
    ).fetchone()[0]
    conn.close()
    return {
        "emails": total,
        "processed": processed,
        "facts": facts,
        "queries": query_count,
        "topics": topic_count,
    }
