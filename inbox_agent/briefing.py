from rich.console import Console

from inbox_agent.query import ask
from inbox_agent.store import load_emails

BRIEFING_QUESTIONS = [
    "What action items or tasks require my attention? List anything I need to reply to, decide on, or do.",
    "Are there any upcoming flights, hotel bookings, or travel plans?",
    "What payments, charges, bills, or financial activity happened?",
    "Did any real people (not automated services) reach out to me? Include LinkedIn messages, recruiter emails, contact form submissions.",
    "Are there any alerts, outages, or service issues I should know about?",
]

SECTION_NAMES = [
    "Action Items",
    "Travel",
    "Money",
    "People",
    "Alerts",
]


def print_briefing(days: int = 7, console: Console | None = None) -> None:
    out = console or Console()
    emails = load_emails()

    if not emails:
        out.print("[dim]No emails stored. Run 'inbox-agent fetch' first.[/dim]")
        return

    # Filter to recent emails
    from datetime import datetime, timezone
    cutoff = datetime.now(timezone.utc).timestamp() - (days * 86400)
    recent = []
    for e in emails:
        try:
            ts = datetime.fromisoformat(e.get("received_at", "")).timestamp()
        except (ValueError, TypeError):
            ts = 0
        if ts >= cutoff:
            recent.append(e)

    if not recent:
        out.print(f"[dim]No emails from the last {days} days.[/dim]")
        return

    out.print(f"[dim]Querying {len(recent)} emails from the last {days} days...[/dim]\n")

    for section_name, question in zip(SECTION_NAMES, BRIEFING_QUESTIONS):
        answer = ask(question, recent)
        stripped = answer.strip()
        if not stripped or stripped.lower().startswith("there are no") or stripped.lower().startswith("there is no") or stripped.lower() == "none." or stripped.lower() == "none":
            continue
        out.print(f"[bold]{section_name}[/bold]")
        out.print(answer.strip())
        out.print()
