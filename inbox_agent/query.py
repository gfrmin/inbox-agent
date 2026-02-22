import json
import os
from datetime import date

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:latest")

SYSTEM_PROMPT = """\
You are an email assistant with access to the user's email archive, extracted facts,
and prior Q&A history. Today's date is {today}.

Answer thoroughly using ALL relevant evidence from the context below.
When listing multiple items, use bullet points with specific dates, amounts, and names.
Include every matching item you find — do not summarize or omit entries.
If the answer isn't in the context, say so.

After your answer, on a new line, output a JSON line starting with TOPICS: followed by
a JSON array of 1-3 short topic tags relevant to this question, e.g.:
TOPICS: ["travel", "finance"]
"""


def _format_emails(emails: list[dict]) -> str:
    if not emails:
        return ""
    lines = ["## Recent Emails"]
    for e in emails:
        sender = e.get("sender_name") or e.get("sender") or e.get("from_name") or e.get("from", "unknown")
        lines.append(
            f"- From: {sender} <{e.get('sender', e.get('from', ''))}>\n"
            f"  Date: {e.get('received_at', '')}\n"
            f"  Subject: {e.get('subject', '')}\n"
            f"  Preview: {e.get('preview', '')}"
        )
    return "\n".join(lines)


def _format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return ""
    grouped: dict[str, list[dict]] = {}
    for e in evidence:
        etype = e.get("evidence_type", "other")
        grouped.setdefault(etype, []).append(e)
    section_titles = {
        "entity": "Entities",
        "commitment": "Commitments",
        "topic": "Topics",
        "event": "Events & Dates",
        "deadline": "Deadlines",
        "action_item": "Action Items",
    }
    lines = ["## Extracted Facts"]
    for etype, items in grouped.items():
        title = section_titles.get(etype, etype.replace("_", " ").title())
        lines.append(f"\n### {title}")
        for e in items:
            conf = e.get("confidence", "?")
            lines.append(f"- {e.get('content', '')} [confidence: {conf}]")
    return "\n".join(lines)


def _format_past_queries(queries: list[dict]) -> str:
    if not queries:
        return ""
    lines = ["## Prior Q&A"]
    for q in queries:
        lines.append(f"- Q: {q.get('question', '')}\n  A: {q.get('answer', '')[:200]}")
    return "\n".join(lines)


def _parse_topics(text: str) -> list[str]:
    for line in reversed(text.strip().splitlines()):
        if line.strip().startswith("TOPICS:"):
            raw = line.strip()[len("TOPICS:"):].strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return []
    return []


def _strip_topics_line(text: str) -> str:
    lines = text.strip().splitlines()
    result = []
    for line in lines:
        if not line.strip().startswith("TOPICS:"):
            result.append(line)
    return "\n".join(result).strip()


def ask(question: str, emails: list[dict],
        evidence: list[dict] | None = None,
        past_queries: list[dict] | None = None) -> dict:
    """Returns {"answer": str, "topics": list[str]}"""
    context_parts = [
        _format_emails(emails),
        _format_evidence(evidence or []),
        _format_past_queries(past_queries or []),
    ]
    context = "\n\n".join(part for part in context_parts if part)
    user_message = f"{context}\n\nQuestion: {question}"

    resp = httpx.post(
        f"{OLLAMA_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(today=date.today().isoformat())},
                {"role": "user", "content": user_message},
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    raw_answer = resp.json()["choices"][0]["message"]["content"]

    topics = _parse_topics(raw_answer)
    answer = _strip_topics_line(raw_answer)

    return {"answer": answer, "topics": topics}
