import json
import os
import re

import httpx

from inbox_agent.store import append_evidence, mark_processed

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:latest")

EXTRACTION_PROMPT = """\
Extract structured information from this email. Only extract concrete, specific facts.

Rules:
- Entities: type must be exactly ONE of: person, org, project, place. \
Use the real name, not an email address.
- Commitments: real obligations or completed transactions only — \
NOT marketing offers, promotions, or upsells.
- Topics: 1-2 English words, lowercase, even for non-English emails. \
Categorize broadly (e.g. "finance", "travel", "work") not specific subjects.
- Temporal: real events with dates, not automated timestamps.
- Confidence: reserve 1.0 for unambiguous facts. Use 0.7-0.9 for likely facts. \
Use below 0.5 for uncertain.
- Do NOT extract: marketing offers, unsubscribe links, automated no-reply senders, \
boilerplate footers.

From: {sender_name} <{sender}>
Date: {received_at}
Subject: {subject}
Preview: {preview}

Return JSON with these fields (use empty arrays if nothing fits):
{{
  "entities": [{{"name": "...", "type": "person", "confidence": 0.8}}],
  "commitments": [{{"who": "...", "what": "...", "direction": "inbound", "confidence": 0.7}}],
  "topics": [{{"topic": "finance", "confidence": 0.8}}],
  "temporal": [{{"event": "...", "date": "YYYY-MM-DD", "confidence": 0.7}}]
}}
"""

# Strings that indicate the model echoed the JSON template instead of extracting
_TEMPLATE_LITERALS = {"...", "one-or-two-word-topic", "YYYY-MM-DD", "person|org|project|place", "finance"}

_EMAIL_RE = re.compile(r"@")


def extract_evidence(email: dict) -> list[dict]:
    prompt = EXTRACTION_PROMPT.format(
        sender_name=email.get("sender_name", ""),
        sender=email.get("sender", "unknown"),
        received_at=email.get("received_at", ""),
        subject=email.get("subject", ""),
        preview=email.get("preview", ""),
    )

    resp = httpx.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "format": "json",
            "stream": False,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    raw = resp.json().get("message", {}).get("content", "{}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    facts = []
    email_id = email["id"]

    for entity in data.get("entities", []):
        if not isinstance(entity, dict):
            continue
        name = (entity.get("name") or "").strip()
        etype = (entity.get("type") or "").strip().lower()
        conf = _clamp(entity.get("confidence", 0.5))
        if conf < 0.3 or _is_template(name) or _is_template(etype):
            continue
        if _EMAIL_RE.search(name):
            continue
        if etype not in ("person", "org", "project", "place"):
            continue
        facts.append({
            "email_id": email_id,
            "evidence_type": "entity",
            "content": f"{name} ({etype})",
            "topic": None,
            "confidence": conf,
        })

    for commitment in data.get("commitments", []):
        if not isinstance(commitment, dict):
            continue
        who = (commitment.get("who") or "").strip()
        what = (commitment.get("what") or "").strip()
        direction = (commitment.get("direction") or "").strip().lower()
        conf = _clamp(commitment.get("confidence", 0.5))
        if conf < 0.3 or _is_template(who) or _is_template(what):
            continue
        facts.append({
            "email_id": email_id,
            "evidence_type": "commitment",
            "content": f"{who}: {what} ({direction})",
            "topic": None,
            "confidence": conf,
        })

    for topic in data.get("topics", []):
        if not isinstance(topic, dict):
            continue
        topic_name = (topic.get("topic") or "").strip().lower()
        conf = _clamp(topic.get("confidence", 0.5))
        if conf < 0.3 or not topic_name or _is_template(topic_name):
            continue
        facts.append({
            "email_id": email_id,
            "evidence_type": "topic",
            "content": topic_name,
            "topic": topic_name,
            "confidence": conf,
        })

    for temporal in data.get("temporal", []):
        if not isinstance(temporal, dict):
            continue
        event = (temporal.get("event") or "").strip()
        date = (temporal.get("date") or "").strip()
        conf = _clamp(temporal.get("confidence", 0.5))
        if conf < 0.3 or _is_template(event) or _is_template(date):
            continue
        if not event and not date:
            continue
        facts.append({
            "email_id": email_id,
            "evidence_type": "temporal",
            "content": f"{event} on {date}" if event else date,
            "topic": None,
            "confidence": conf,
        })

    return facts


def _clamp(v, lo=0.0, hi=1.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.5


def _is_template(s: str) -> bool:
    """Return True if the string is a literal from the JSON template."""
    return s in _TEMPLATE_LITERALS


def process_emails(emails: list[dict], log=print) -> tuple[int, int]:
    """Process a batch of emails. Returns (facts_count, topics_count)."""
    all_facts = []
    topics_seen = set()
    total = len(emails)

    for i, email in enumerate(emails, 1):
        subject = email.get("subject", "")[:60]
        log(f"[{i}/{total}] {subject}")
        facts = extract_evidence(email)
        all_facts.extend(facts)
        for f in facts:
            if f.get("topic"):
                topics_seen.add(f["topic"])
        append_evidence(facts)
        mark_processed(email["id"])

    return len(all_facts), len(topics_seen)
