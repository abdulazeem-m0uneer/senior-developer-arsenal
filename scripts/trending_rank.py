#!/usr/bin/env python3
"""Record this repository's position on github.com/trending in README.md.

GitHub has no API for trending, so the public page is parsed. The README block
between the trending markers is rewritten only when a rank actually changes.

Usage:
  python3 scripts/trending_rank.py [--repo owner/name] [--readme README.md]

Exit codes: 0 README updated or already current, 1 the page could not be read
or parsed (README left untouched).
"""
import argparse
import datetime
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "abdulazeem-m0uneer/senior-developer-arsenal"
TRENDING_URL = "https://github.com/trending?since={period}"
PERIODS = (("daily", "Today"), ("weekly", "This week"), ("monthly", "This month"))
BEGIN, END = "<!-- BEGIN trending -->", "<!-- END trending -->"
REPO_LINK_RE = re.compile(r'<h2 class="h3 lh-condensed">.*?href="/([^"/]+/[^"/]+)"', re.DOTALL)
TIMEOUT_SECONDS = 30


class TrendingError(Exception):
    """The trending page could not be fetched or understood."""


def fetch_trending(period):
    request = urllib.request.Request(
        TRENDING_URL.format(period=period), headers={"User-Agent": "senior-developer-arsenal-trending"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TrendingError(f"could not fetch the {period} trending page: {error}") from error
    repositories = [match.lower() for match in REPO_LINK_RE.findall(html)]
    if not repositories:
        raise TrendingError(f"no repositories found on the {period} trending page; its markup may have changed")
    return repositories


def describe_rank(repository, trending):
    if repository.lower() in trending:
        return f"**#{trending.index(repository.lower()) + 1}**"
    return "Not trending"


def render_rows(repository):
    return [f"| {label} | {describe_rank(repository, fetch_trending(period))} |" for period, label in PERIODS]


def render_block(rows, date):
    return "\n".join([
        BEGIN,
        "| Period | Rank on [GitHub Trending](https://github.com/trending) |",
        "| :--- | :--- |",
        *rows,
        "",
        f"_Last change detected: {date} (UTC). Checked daily by `.github/workflows/trending.yml`._",
        END,
    ])


def update_readme(text, rows, date):
    """Return the new README text, or None when the ranks are unchanged."""
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(BEGIN) > text.index(END):
        raise TrendingError("README must contain exactly one trending block (BEGIN before END)")
    start, stop = text.index(BEGIN), text.index(END) + len(END)
    current_rows = [line for line in text[start:stop].splitlines()
                    if line.startswith("| ") and not line.startswith(("| Period", "| :"))]
    if current_rows == rows:
        return None
    return text[:start] + render_block(rows, date) + text[stop:]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO))
    parser.add_argument("--readme", default=str(Path(__file__).resolve().parent.parent / "README.md"))
    options = parser.parse_args(argv)

    readme = Path(options.readme)
    try:
        rows = render_rows(options.repo)
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        updated = update_readme(readme.read_text(encoding="utf-8"), rows, today)
    except (TrendingError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if updated is None:
        print("trending rank unchanged")
        return 0
    readme.write_text(updated, encoding="utf-8", newline="\n")
    print("trending rank updated:\n" + "\n".join(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
