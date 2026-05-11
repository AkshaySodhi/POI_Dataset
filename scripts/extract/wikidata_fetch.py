import json
import requests
import pandas as pd
from pathlib import Path
from time import sleep
from collections import defaultdict

SPARQL_URL = "https://query.wikidata.org/sparql"

QUERY_TEMPLATE = """
SELECT ?place ?placeLabel ?coord ?image ?countryLabel ?article WHERE {
  ?place wdt:P31/wdt:P279* wd:%s.
  ?place wdt:P625 ?coord.
  ?place wdt:P18 ?image.

  OPTIONAL { ?place wdt:P17 ?country. }
  OPTIONAL {
    ?article schema:about ?place ;
             schema:isPartOf <https://en.wikipedia.org/>.
  }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en".
  }
}
LIMIT %s
OFFSET %s
"""

HEADERS = {
    "User-Agent": "GlobalPOIBuilder/1.0 (akshaysodhi422@gmail.com)"
}

# ── Balance config ────────────────────────────────────────────────────────────

# No country can contribute more than this fraction of a category's global target.
# e.g. if target=800 for history_and_mysteries, no country gets more than 800*0.15=120
MAX_COUNTRY_SHARE = 0.15

# Hard cap: even for very large targets, no single country exceeds this per category.
MAX_PER_COUNTRY_PER_CATEGORY = 80

# Countries with a huge amount of well-documented Wikidata entries.
# They get a slightly higher share since they genuinely have more places.
HIGH_POI_COUNTRIES = {
    "United States", "United Kingdom", "Germany", "France", "Italy",
    "India", "China", "Japan", "Spain", "Russia", "Australia", "Brazil",
    "Canada", "Mexico", "Turkey", "Greece", "Egypt", "Iran", "Indonesia",
    "Poland", "Netherlands", "Sweden", "Norway", "Switzerland", "Austria",
}
HIGH_POI_SHARE_BONUS = 0.05   # +5% share for high-POI countries


# ── Helpers ───────────────────────────────────────────────────────────────────

def country_cap(country: str, target: int) -> int:
    """
    Calculate the max POIs allowed for a single country within a category.
    """
    share = MAX_COUNTRY_SHARE
    if country in HIGH_POI_COUNTRIES:
        share += HIGH_POI_SHARE_BONUS
    cap = int(target * share)
    return min(cap, MAX_PER_COUNTRY_PER_CATEGORY)


def run_query(query: str, retries: int = 6):
    for attempt in range(retries):
        try:
            response = requests.get(
                SPARQL_URL,
                params={"format": "json", "query": query},
                headers=HEADERS,
                timeout=180
            )
            if response.status_code in [429, 500, 502, 503, 504]:
                wait_time = 5 * (attempt + 1)
                print(f"  Server error {response.status_code}. Retrying in {wait_time}s...")
                sleep(wait_time)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            wait_time = 5 * (attempt + 1)
            print(f"  Request failed: {e}. Retrying in {wait_time}s...")
            sleep(wait_time)
    raise Exception("Failed after retries")


def parse_results(data, category):
    rows = []
    for item in data["results"]["bindings"]:
        image_url = item.get("image", {}).get("value")
        if not image_url:
            continue
        rows.append({
            "wikidata_id": item.get("place", {}).get("value", "").split("/")[-1],
            "name": item.get("placeLabel", {}).get("value"),
            "category": category,
            "coordinates": item.get("coord", {}).get("value"),
            "image_url": image_url,
            "country": item.get("countryLabel", {}).get("value"),
            "wikipedia_url": item.get("article", {}).get("value")
        })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open("config/categories.json", "r", encoding="utf-8") as f:
        categories = json.load(f)

    with open("config/targets.json", "r", encoding="utf-8") as f:
        targets = json.load(f)

    all_rows = []
    limit = 200  # results per SPARQL page

    for category, qid in categories.items():
        target_count = targets.get(category, 0)

        if target_count == 0:
            print(f"Skipping {category} (no target count set)")
            continue

        print(f"\n{'='*60}")
        print(f"  Category : {category}  |  Target: {target_count}")
        print(f"{'='*60}")

        offset = 0
        collected = 0                          # total accepted for this category
        country_counts = defaultdict(int)      # per-country accepted counts
        seen_ids = set()                       # deduplicate within category

        consecutive_empty_pages = 0

        while collected < target_count:
            query = QUERY_TEMPLATE % (qid, limit, offset)

            try:
                data = run_query(query)
                rows = parse_results(data, category)
            except Exception as e:
                print(f"  ERROR at offset {offset}: {e}. Skipping category.")
                break

            if not rows:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 2:
                    print(f"  No more results. Stopping early at {collected}/{target_count}.")
                    break
                offset += limit
                sleep(4)
                continue

            consecutive_empty_pages = 0
            accepted_this_page = 0

            for row in rows:
                wid = row["wikidata_id"]
                country = row.get("country") or "Unknown"

                # Skip already-seen wikidata IDs (handles multi-country rows)
                if wid in seen_ids:
                    continue

                # Skip if this country has hit its per-category cap
                cap = country_cap(country, target_count)
                if country_counts[country] >= cap:
                    continue

                # Accept this row
                seen_ids.add(wid)
                country_counts[country] += 1
                all_rows.append(row)
                collected += 1
                accepted_this_page += 1

                if collected >= target_count:
                    break

            print(f"  Offset {offset:>6} | Page results: {len(rows):>3} | "
                  f"Accepted: {accepted_this_page:>3} | Total: {collected}/{target_count}")

            offset += limit
            sleep(4)

        # Per-category country breakdown
        top_countries = sorted(country_counts.items(), key=lambda x: -x[1])[:8]
        print(f"\n  Country distribution (top 8):")
        for c, n in top_countries:
            bar = "█" * n
            print(f"    {c:<30} {n:>4}  {bar}")

    df = pd.DataFrame(all_rows)
    df = df[df["image_url"].notna()]

    Path("data/raw").mkdir(parents=True, exist_ok=True)
    output = "data/raw/wikidata_pois_images_only.csv"
    df.to_csv(output, index=False)

    print(f"\n{'='*60}")
    print(f"  DONE")
    print(f"  Saved  : {output}")
    print(f"  Total  : {len(df)} rows")

    # Global category summary
    print(f"\n  Category summary:")
    for cat, grp in df.groupby("category"):
        print(f"    {cat:<30} {len(grp):>5} POIs  |  "
              f"{grp['country'].nunique()} countries")


if __name__ == "__main__":
    main()
