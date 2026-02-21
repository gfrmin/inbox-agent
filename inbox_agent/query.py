import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:latest")

SYSTEM_PROMPT = """\
You are an email assistant. You will be given a list of recent emails and a question.
Answer the question based only on the emails provided. Be concise and direct.
If the answer isn't in the emails, say so.
"""


def _format_emails_for_context(emails: list[dict]) -> str:
    lines = []
    for e in emails:
        sender = e.get("from_name") or e.get("from", "unknown")
        lines.append(
            f"- From: {sender} <{e.get('from', '')}>\n"
            f"  Date: {e.get('received_at', '')}\n"
            f"  Subject: {e.get('subject', '')}\n"
            f"  Preview: {e.get('preview', '')}"
        )
    return "\n".join(lines)


def ask(question: str, emails: list[dict]) -> str:
    context = _format_emails_for_context(emails)
    user_message = f"Here are the recent emails:\n\n{context}\n\nQuestion: {question}"

    resp = httpx.post(
        f"{OLLAMA_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
