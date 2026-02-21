from rich.console import Console

from inbox_agent.query import ask
from inbox_agent.store import (
    get_topic_weights,
    log_query,
    search_emails,
    search_evidence,
    search_queries,
)

SEED_QUESTIONS = [
    ("Action Items", "What action items or tasks require my attention? List anything I need to reply to, decide on, or do."),
    ("Upcoming Events", "Are there any upcoming events, flights, hotel bookings, or travel plans?"),
    ("Alerts", "Are there any alerts, outages, or important notifications I should know about?"),
]


def _build_sections() -> list[tuple[str, str]]:
    """Build briefing sections from topic weights, falling back to seeds."""
    weights = get_topic_weights()
    if not weights:
        return SEED_QUESTIONS

    sections = []
    for topic, _ in weights[:5]:
        sections.append((topic.title(), f"What's new about {topic}? Summarize recent activity."))

    sections.append(("Action Items", "What action items or tasks need my attention? List anything I need to reply to, decide on, or do."))
    return sections


def print_briefing(days: int = 7, console: Console | None = None) -> None:
    out = console or Console()
    emails = search_emails(days=days, limit=50)

    if not emails:
        out.print(f"[dim]No emails from the last {days} days. Run 'inbox-agent fetch' first.[/dim]")
        return

    sections = _build_sections()
    out.print(f"[dim]Briefing from {len(emails)} emails over the last {days} days...[/dim]\n")

    for section_name, question in sections:
        relevant_evidence = search_evidence(section_name.lower(), limit=20)
        past = search_queries(section_name.lower(), limit=5)

        result = ask(question, emails, evidence=relevant_evidence, past_queries=past)
        answer = result["answer"].strip()
        topics = result["topics"]

        if not answer or _is_empty_answer(answer):
            continue

        out.print(f"[bold]{section_name}[/bold]")
        out.print(answer)
        out.print()

        log_query(question, answer, [e["id"] for e in emails[:10]], topics or [section_name.lower()])


def _is_empty_answer(answer: str) -> bool:
    lower = answer.lower().strip()
    empty_patterns = [
        "there are no", "there is no", "none.", "none",
        "no relevant", "i don't see any", "i don't find any",
        "nothing to report", "no information",
    ]
    return any(lower.startswith(p) or lower == p for p in empty_patterns)
