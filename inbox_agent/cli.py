import click
from dotenv import load_dotenv
from rich.console import Console

from inbox_agent.jmap import JMAPClient
from inbox_agent.store import append_emails, emails_path, load_email_ids

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
    total = len(load_email_ids())

    if new_count:
        console.print(f"[green]Stored {new_count} new emails.[/green] ({total} total)")
    else:
        console.print(f"[dim]No new emails. ({total} total)[/dim]")
    console.print(f"[dim]{emails_path()}[/dim]")


@cli.command()
@click.argument("question")
def ask(question: str):
    """Ask a question about your stored emails."""
    from inbox_agent.query import ask as do_ask
    from inbox_agent.store import load_emails

    emails = load_emails()
    if not emails:
        console.print("[dim]No emails stored. Run 'inbox-agent fetch' first.[/dim]")
        return

    console.print(f"[dim]Searching {len(emails)} emails...[/dim]\n")
    answer = do_ask(question, emails)
    console.print(answer)


@cli.command()
@click.option("--days", default=7, type=int, help="How many days back to include.")
def briefing(days: int):
    """Run known questions against recent emails and print a summary."""
    from inbox_agent.briefing import print_briefing

    print_briefing(days=days, console=console)
