"""
fetch_wikipedia_descriptions.py
--------------------------------
Adapted from enrich_wiki.py for the Global POIs pipeline.

Reads:  data/processed/pois_clean.csv
Writes: data/processed/pois_descriptions.csv

For each POI:
  - If `wikipedia_url` exists → fetch the intro section directly (accurate, fast)
  - If no `wikipedia_url`     → fall back to searching Wikipedia by name

Fetches the first 3 paragraphs of the article intro as the description
(much richer than Wikidata's one-liners).

All existing columns are preserved. Only the `description` column is added/updated.

Resumable: re-running skips rows that already have a description.

Usage:
    pip install wikipedia-api
    python scripts/enrich/fetch_wikipedia_descriptions.py
"""

import csv
import time
import re
from pathlib import Path

import wikipediaapi

# ── Config ────────────────────────────────────────────────────────────────────
INPUT_FILE  = "data/processed/pois_clean.csv"
OUTPUT_FILE = "data/processed/pois_descriptions.csv"

DELAY_SECONDS  = 0.5   # polite delay between API calls
MAX_PARAGRAPHS = 3     # how many intro paragraphs to keep
MAX_CHARS      = 1000  # hard cap on description length

# ── Wikipedia client ──────────────────────────────────────────────────────────
wiki = wikipediaapi.Wikipedia(
    user_agent="GlobalPOIBuilder/1.0 (akshaysodhi422@gmail.com)",
    language="en",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def slug_from_url(wikipedia_url: str) -> str:
    """
    Extract the article title slug from a Wikipedia URL.
    e.g. https://en.wikipedia.org/wiki/Birka  →  Birka
    """
    match = re.search(r"/wiki/(.+)$", wikipedia_url or "")
    return match.group(1).replace("_", " ") if match else ""


def fetch_page_by_url(wikipedia_url: str):
    """Fetch a WikipediaPage using the article slug from the URL."""
    title = slug_from_url(wikipedia_url)
    if not title:
        return None
    page = wiki.page(title)
    return page if page.exists() else None


def fetch_page_by_name(name: str):
    """Fall back: search Wikipedia by place name."""
    results = wiki.search(name, limit=1)
    if not results or not results.pages:
        return None
    for _, page in results.pages.items():
        if page.exists():
            return page
    return None


def extract_description(page) -> str:
    """
    Pull the first MAX_PARAGRAPHS paragraphs from the article summary.
    Cleans up extra whitespace and trims to MAX_CHARS.
    """
    summary = page.summary or ""

    # Split on blank lines to get paragraphs
    paragraphs = [p.strip() for p in summary.split("\n\n") if p.strip()]

    # Take first N paragraphs
    selected = paragraphs[:MAX_PARAGRAPHS]
    description = "\n\n".join(selected)

    # Hard cap
    if len(description) > MAX_CHARS:
        description = description[:MAX_CHARS - 3] + "..."

    return description


def enrich_row(name: str, wikipedia_url: str) -> str:
    """
    Return a description string for this POI.
    Returns '' if nothing found.
    """
    page = None

    # Prefer direct URL lookup — it's exact
    if wikipedia_url and wikipedia_url.strip():
        page = fetch_page_by_url(wikipedia_url.strip())
        if page:
            print(f"  → Via URL: '{page.title}'")

    # Fall back to name search
    if not page:
        page = fetch_page_by_name(name)
        if page:
            print(f"  → Via search: '{page.title}'")

    if not page:
        print(f"  → Not found.")
        return ""

    return extract_description(page)


# ── Resume support ────────────────────────────────────────────────────────────

def load_done(output_path: Path) -> dict:
    """
    Load already-processed rows from the output file.
    Returns a dict of {wikidata_id: description} so we can skip them.
    Falls back to name-based keying if wikidata_id column is absent.
    """
    done = {}
    if not output_path.exists():
        return done
    try:
        with open(output_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                desc = row.get("description", "").strip()
                if not desc:
                    continue  # don't count empty descriptions as done
                key = row.get("wikidata_id") or row.get("name", "")
                if key:
                    done[key] = desc
    except Exception:
        pass
    return done


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    in_path  = Path(INPUT_FILE)
    out_path = Path(OUTPUT_FILE)

    if not in_path.exists():
        print(f"ERROR: Input file not found: {in_path}")
        return

    with open(in_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []

    # Make sure description column exists in output
    if "description" not in fieldnames:
        fieldnames.append("description")

    done = load_done(out_path)
    if done:
        print(f"Resuming — {len(done)} row(s) already have descriptions.\n")

    # Write mode: append if resuming, fresh write if new
    is_new = not out_path.exists() or out_path.stat().st_size == 0
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_file = open(out_path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_file, fieldnames=fieldnames, extrasaction="ignore")
    if is_new:
        writer.writeheader()

    processed = skipped = failed = 0
    total = len(rows)

    try:
        for i, row in enumerate(rows, 1):
            key = row.get("wikidata_id") or row.get("name", "")
            name = row.get("name", "")
            wikipedia_url = row.get("wikipedia_url", "")

            # Skip if already done
            if key in done:
                skipped += 1
                print(f"[{i}/{total}] Skipping (done): {name}")
                continue

            print(f"[{i}/{total}] Fetching: {name}")
            description = enrich_row(name, wikipedia_url)

            if description:
                processed += 1
            else:
                failed += 1

            out_row = dict(row)
            out_row["description"] = description
            writer.writerow(out_row)
            out_file.flush()

            time.sleep(DELAY_SECONDS)

    finally:
        out_file.close()

    print(f"\n{'='*50}")
    print(f"Done!")
    print(f"  Enriched : {processed}")
    print(f"  Skipped  : {skipped}")
    print(f"  Not found: {failed}")
    print(f"  Output   : {out_path}")


if __name__ == "__main__":
    main()
