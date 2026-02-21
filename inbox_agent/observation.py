import json
import os

import httpx

from inbox_agent.store import append_evidence, mark_processed

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:latest")

EXTRACTION_PROMPT = """\
Extract structured information from this email. For each item, rate your
confidence (0.0-1.0). Only extract concrete, specific facts.

From: {sender_name} <{sender}>
Date: {received_at}
Subject: {subject}
Preview: {preview}

Return JSON:
{{
  "entities": [{{"name": "...", "type": "person|org|project|place", "confidence": 0.0}}],
  "commitments": [{{"who": "...", "what": "...", "direction": "inbound|outbound", "confidence": 0.0}}],
  "topics": [{{"topic": "one-or-two-word-topic", "confidence": 0.0}}],
  "temporal": [{{"event": "...", "date": "...", "confidence": 0.0}}]
}}
"""


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
        facts.append({
            "email_id": email_id,
            "evidence_type": "entity",
            "content": f"{entity.get('name', '')} ({entity.get('type', '')})",
            "topic": None,
            "confidence": _clamp(entity.get("confidence", 0.5)),
        })

    for commitment in data.get("commitments", []):
        facts.append({
            "email_id": email_id,
            "evidence_type": "commitment",
            "content": f"{commitment.get('who', '')}: {commitment.get('what', '')} ({commitment.get('direction', '')})",
            "topic": None,
            "confidence": _clamp(commitment.get("confidence", 0.5)),
        })

    for topic in data.get("topics", []):
        topic_name = topic.get("topic", "").strip().lower()
        if topic_name:
            facts.append({
                "email_id": email_id,
                "evidence_type": "topic",
                "content": topic_name,
                "topic": topic_name,
                "confidence": _clamp(topic.get("confidence", 0.5)),
            })

    for temporal in data.get("temporal", []):
        event = temporal.get("event", "").strip()
        date = temporal.get("date", "").strip()
        if not event and not date:
            continue
        facts.append({
            "email_id": email_id,
            "evidence_type": "temporal",
            "content": f"{event} on {date}" if event else date,
            "topic": None,
            "confidence": _clamp(temporal.get("confidence", 0.5)),
        })

    return facts


def _clamp(v, lo=0.0, hi=1.0) -> float:
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return 0.5


def process_emails(emails: list[dict]) -> tuple[int, int]:
    """Process a batch of emails. Returns (facts_count, topics_count)."""
    all_facts = []
    topics_seen = set()

    for email in emails:
        facts = extract_evidence(email)
        all_facts.extend(facts)
        for f in facts:
            if f.get("topic"):
                topics_seen.add(f["topic"])
        append_evidence(facts)
        mark_processed(email["id"])

    return len(all_facts), len(topics_seen)
