# DataDiver

Modern async web scraper for extracting metadata and structure from websites.

## Features

- **Async crawling** - Concurrent requests for 10x faster performance
- **Beautiful CLI** - Rich terminal output with progress bars
- **Smart filtering** - Automatically skips images, PDFs, pagination, and non-content pages
- **SEO metadata** - Extracts titles, meta descriptions, H1/H2 headings
- **CSV export** - Clean, organized output for analysis

## Requirements

- Python 3.12+ (or Docker)

## Installation

### With Docker (recommended)

```bash
# Build the image
docker build -t datadiver .

# Run
docker run --rm -v $(pwd)/output:/output datadiver https://example.com

# Or use docker-compose
docker compose run --rm datadiver https://example.com --max 200
```

### With Python

```bash
# Clone the repository
git clone https://github.com/MrGKanev/DataDiver.git
cd DataDiver

# Install with pip
pip install -e .

# Or install dependencies directly
pip install httpx beautifulsoup4 lxml rich typer aiofiles
```

## Usage

### Basic crawl

```bash
datadiver https://example.com
```

### With options

```bash
# Crawl up to 500 pages with 20 concurrent requests
datadiver https://example.com --max 500 --concurrency 20

# Custom output file
datadiver https://example.com -o results.csv

# Quiet mode (minimal output)
datadiver https://example.com -q
```

### All options

```
Usage: datadiver [OPTIONS] URL

Arguments:
  URL  The URL to start crawling from [required]

Options:
  -m, --max INTEGER        Maximum pages to crawl [default: 100]
  -c, --concurrency INTEGER  Concurrent requests [default: 10]
  -t, --timeout FLOAT      Request timeout in seconds [default: 30.0]
  -o, --output PATH        Output CSV file path
  -q, --quiet              Minimal output
  --help                   Show this message and exit
```

## Output

The CSV output includes:

| Column | Description |
|--------|-------------|
| Status Code | HTTP response code |
| URL | Page URL |
| Title | Page title |
| Meta Description | SEO meta description |
| H1-1, H1-2, ... | H1 headings |
| H2-1, H2-2, ... | H2 headings |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linter
ruff check .

# Run type checker
mypy datadiver.py

# Run tests
pytest
```

## License

MIT License - Gabriel Kanev
