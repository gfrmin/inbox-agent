import click
from dotenv import load_dotenv
from rich.console import Console

from inbox_agent.jmap import JMAPClient
from inbox_agent.store import (
    append_emails,
    db_path,
    email_count,
    log_query,
    search,
)

load_dotenv()

console = Console()


@click.group()
def cli():
    """inbox-agent — personal email knowledge pipeline."""


@cli.command()
@click.option("--limit", default=500, type=int, help="Max emails to fetch.")
def fetch(limit: int):
    """Fetch inbox emails and store metadata locally."""
    client = JMAPClient()
    console.print("Fetching inbox emails...")
    emails = client.get_inbox_emails(limit=limit)
    console.print(f"Fetched {len(emails)} from Fastmail.")

    new_count = append_emails(emails)
    total = email_count()

    if new_count:
        console.print(f"[green]Stored {new_count} new emails.[/green] ({total} total)")
    else:
        console.print(f"[dim]No new emails. ({total} total)[/dim]")
    console.print(f"[dim]{db_path()}[/dim]")


@cli.command()
@click.option("--limit", default=None, type=int, help="Max emails to process.")
def process(limit: int | None):
    """Extract structured facts from unprocessed emails."""
    from inbox_agent.observation import process_emails
    from inbox_agent.store import get_unprocessed

    unprocessed = get_unprocessed()
    if not unprocessed:
        console.print("[dim]No unprocessed emails.[/dim]")
        return

    batch = unprocessed[:limit] if limit else unprocessed
    console.print(f"Processing {len(batch)} of {len(unprocessed)} unprocessed emails...")
    facts_count, topics_count = process_emails(batch)
    console.print(
        f"[green]{facts_count} facts extracted, {topics_count} topics discovered.[/green]"
    )


@cli.command()
@click.argument("question")
def ask(question: str):
    """Ask a question about your stored emails."""
    from inbox_agent.query import ask as do_ask

    results = search(question, limit=30)
    emails = results["emails"]
    evidence = results["evidence"]
    past_queries = results["queries"]

    if not emails and not evidence:
        console.print("[dim]No emails stored. Run 'inbox-agent fetch' first.[/dim]")
        return

    parts = []
    if emails:
        parts.append(f"{len(emails)} emails")
    if evidence:
        parts.append(f"{len(evidence)} facts")
    if past_queries:
        parts.append(f"{len(past_queries)} prior Q&A")
    console.print(f"[dim]Searching {', '.join(parts)}...[/dim]\n")

    result = do_ask(question, emails, evidence=evidence, past_queries=past_queries)
    console.print(result["answer"])

    log_query(
        question,
        result["answer"],
        [e["id"] for e in emails[:10]],
        result["topics"],
    )


@cli.command()
@click.option("--days", default=7, type=int, help="How many days back to include.")
def briefing(days: int):
    """Run adaptive topic-driven briefing against recent emails."""
    from inbox_agent.briefing import print_briefing

    print_briefing(days=days, console=console)


@cli.command()
def status():
    """Show knowledge base statistics."""
    from inbox_agent.store import get_topic_weights, status as get_status

    s = get_status()
    console.print(f"[bold]Emails:[/bold]      {s['emails']}")
    console.print(f"[bold]Processed:[/bold]   {s['processed']}")
    console.print(f"[bold]Facts:[/bold]       {s['facts']}")
    console.print(f"[bold]Queries:[/bold]     {s['queries']}")
    console.print(f"[bold]Topics:[/bold]      {s['topics']}")

    weights = get_topic_weights()
    if weights:
        console.print(f"\n[bold]Top topics:[/bold]")
        for topic, count in weights[:10]:
            console.print(f"  {topic}: {count}")

    console.print(f"\n[dim]{db_path()}[/dim]")
