#!/usr/bin/env python3
"""DataDiver - Modern async web scraper for metadata extraction."""

from __future__ import annotations

import asyncio
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

import httpx
import typer
from bs4 import BeautifulSoup
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table

if TYPE_CHECKING:
    from collections.abc import Set

app = typer.Typer(
    name="datadiver",
    help="Modern async web scraper for extracting metadata from websites.",
    add_completion=False,
)
console = Console()

EXCLUDED_EXTENSIONS = frozenset([
    "png", "jpg", "jpeg", "gif", "webp", "svg", "ico", "bmp",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "zip", "rar", "7z", "tar", "gz",
    "mp3", "mp4", "avi", "mov", "wmv", "flv",
    "css", "js", "woff", "woff2", "ttf", "eot",
])

EXCLUDED_PATHS = frozenset([
    "cart", "checkout", "search", "login", "logout", "register",
    "terms-of-service", "privacy-policy", "wp-admin", "wp-login",
    "feed", "xmlrpc", "wp-json", "api",
])

PAGINATION_PATTERNS = re.compile(
    r"\?page=|\?p=|\?pg=|\?pagenumber=|\?start=|\?offset=|/page/|/p/|/pages/|#page=",
    re.IGNORECASE,
)


@dataclass
class PageData:
    """Data extracted from a single page."""

    url: str
    status_code: int
    title: str = ""
    meta_description: str = ""
    h1_tags: list[str] = field(default_factory=list)
    h2_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, str | int]:
        """Convert to flat dictionary for CSV export."""
        data: dict[str, str | int] = {
            "Status Code": self.status_code,
            "URL": self.url,
            "Title": self.title,
            "Meta Description": self.meta_description,
        }
        for i, h1 in enumerate(self.h1_tags, 1):
            data[f"H1-{i}"] = h1
        for i, h2 in enumerate(self.h2_tags, 1):
            data[f"H2-{i}"] = h2
        return data


@dataclass
class CrawlStats:
    """Statistics for the crawl operation."""

    pages_crawled: int = 0
    pages_failed: int = 0
    pages_filtered: int = 0
    total_links_found: int = 0


def normalize_url(url: str) -> str:
    """Normalize URL to lowercase without trailing slash."""
    return url.lower().rstrip("/")


def get_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def sanitize_url(url: str) -> str:
    """Ensure URL has a valid scheme."""
    if not re.match(r"https?://", url, re.IGNORECASE):
        url = "https://" + url
    return normalize_url(url)


def is_valid_link(link: str, domain: str) -> bool:
    """Check if a link should be crawled."""
    if get_domain(link) != domain:
        return False
    if "#" in link or "?" in link:
        return False
    if PAGINATION_PATTERNS.search(link):
        return False

    link_lower = link.lower()
    if any(f".{ext}" in link_lower for ext in EXCLUDED_EXTENSIONS):
        return False
    if any(path in link_lower for path in EXCLUDED_PATHS):
        return False

    return True


async def fetch_page(
    client: httpx.AsyncClient,
    url: str,
    domain: str,
) -> tuple[PageData | None, list[str]]:
    """Fetch and parse a single page."""
    try:
        response = await client.get(url, follow_redirects=True)
        content_type = response.headers.get("content-type", "")

        if "text/html" not in content_type:
            return None, []

        soup = BeautifulSoup(response.text, "lxml")

        page_data = PageData(
            url=url,
            status_code=response.status_code,
            title=soup.title.string.strip() if soup.title and soup.title.string else "",
            meta_description="",
            h1_tags=[tag.get_text(strip=True) for tag in soup.find_all("h1")],
            h2_tags=[tag.get_text(strip=True) for tag in soup.find_all("h2")],
        )

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            page_data.meta_description = meta_desc["content"].strip()

        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            full_url = normalize_url(urljoin(url, anchor["href"]))
            if is_valid_link(full_url, domain):
                links.append(full_url)

        return page_data, links

    except httpx.HTTPError:
        return None, []
    except Exception:
        return None, []


async def crawl_site(
    start_url: str,
    max_pages: int,
    concurrency: int,
    timeout: float,
) -> tuple[list[PageData], CrawlStats]:
    """Crawl a website asynchronously."""
    domain = get_domain(start_url)
    visited: set[str] = set()
    to_visit: set[str] = {start_url}
    results: list[PageData] = []
    stats = CrawlStats()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        console=console,
    )

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=concurrency),
        headers={"User-Agent": "DataDiver/1.0 (+https://github.com/MrGKanev/DataDiver)"},
    ) as client:
        with Live(progress, console=console, refresh_per_second=10):
            task_id: TaskID = progress.add_task("Crawling...", total=max_pages)

            while to_visit and stats.pages_crawled < max_pages:
                batch = set()
                while to_visit and len(batch) < concurrency:
                    url = to_visit.pop()
                    if url not in visited:
                        visited.add(url)
                        batch.add(url)

                if not batch:
                    break

                tasks = [fetch_page(client, url, domain) for url in batch]
                responses = await asyncio.gather(*tasks)

                for page_data, links in responses:
                    if page_data:
                        results.append(page_data)
                        stats.pages_crawled += 1
                        stats.total_links_found += len(links)

                        for link in links:
                            if link not in visited and len(to_visit) + len(visited) < max_pages * 2:
                                to_visit.add(link)
                    else:
                        stats.pages_filtered += 1

                    progress.update(task_id, completed=stats.pages_crawled)

    return results, stats


def export_to_csv(results: list[PageData], output_path: Path) -> None:
    """Export results to CSV file."""
    if not results:
        return

    all_keys: set[str] = set()
    rows = [page.to_dict() for page in results]
    for row in rows:
        all_keys.update(row.keys())

    base_columns = ["Status Code", "URL", "Title", "Meta Description"]
    h1_cols = sorted([k for k in all_keys if k.startswith("H1-")], key=lambda x: int(x.split("-")[1]))
    h2_cols = sorted([k for k in all_keys if k.startswith("H2-")], key=lambda x: int(x.split("-")[1]))
    fieldnames = base_columns + h1_cols + h2_cols

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def display_results(results: list[PageData], stats: CrawlStats) -> None:
    """Display crawl results in a pretty table."""
    table = Table(title="Crawl Results", show_lines=True)
    table.add_column("Status", style="cyan", width=6)
    table.add_column("URL", style="blue", max_width=60)
    table.add_column("Title", style="green", max_width=40)

    for page in results[:20]:
        status_style = "green" if page.status_code == 200 else "yellow"
        table.add_row(
            f"[{status_style}]{page.status_code}[/{status_style}]",
            page.url[:60] + "..." if len(page.url) > 60 else page.url,
            page.title[:40] + "..." if len(page.title) > 40 else page.title,
        )

    if len(results) > 20:
        table.add_row("...", f"[dim]and {len(results) - 20} more pages[/dim]", "")

    console.print(table)

    stats_panel = Panel(
        f"[green]Pages crawled:[/green] {stats.pages_crawled}\n"
        f"[yellow]Pages filtered:[/yellow] {stats.pages_filtered}\n"
        f"[blue]Total links found:[/blue] {stats.total_links_found}",
        title="Statistics",
        border_style="blue",
    )
    console.print(stats_panel)


@app.command()
def crawl(
    url: str = typer.Argument(..., help="The URL to start crawling from"),
    max_pages: int = typer.Option(100, "--max", "-m", help="Maximum pages to crawl"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Concurrent requests"),
    timeout: float = typer.Option(30.0, "--timeout", "-t", help="Request timeout in seconds"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output CSV file path"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
) -> None:
    """Crawl a website and extract metadata."""
    start_url = sanitize_url(url)
    domain = get_domain(start_url)

    if not quiet:
        console.print(
            Panel(
                f"[bold]Target:[/bold] {start_url}\n"
                f"[bold]Domain:[/bold] {domain}\n"
                f"[bold]Max pages:[/bold] {max_pages}\n"
                f"[bold]Concurrency:[/bold] {concurrency}",
                title="DataDiver v1.0",
                border_style="green",
            )
        )

    results, stats = asyncio.run(crawl_site(start_url, max_pages, concurrency, timeout))

    if not results:
        console.print("[red]No pages were crawled successfully.[/red]")
        raise typer.Exit(1)

    if not quiet:
        display_results(results, stats)

    if output is None:
        safe_domain = re.sub(r"[^\w\-]", "_", domain.replace("https://", "").replace("http://", ""))
        output = Path(f"{safe_domain}_crawl.csv")

    export_to_csv(results, output)
    console.print(f"\n[green]Results exported to:[/green] {output}")


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold]DataDiver[/bold] v1.0.0")
    console.print("Modern async web scraper for metadata extraction")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
