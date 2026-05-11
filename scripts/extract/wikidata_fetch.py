import json
import requests
import pandas as pd
from pathlib import Path
from time import sleep
from collections import defaultdict

SPARQL_URL = "https://query.wikidata.org/sparql"

QUERY_TEMPLATE = """
SELECT ?place ?placeLabel ?coord ?image ?countryLabel ?article (COUNT(?sitelink) AS ?sitelinks) WHERE {
  ?place wdt:P31/wdt:P279* wd:%s.
  ?place wdt:P625 ?coord.
  ?place wdt:P18 ?image.

  OPTIONAL { ?place wdt:P17 ?country. }
  OPTIONAL {
    ?article schema:about ?place ;
             schema:isPartOf <https://en.wikipedia.org/>.
  }

  # Count sitelinks as popularity proxy — Taj Mahal ~100, obscure place ~3
  OPTIONAL { ?sitelink schema:about ?place. }

  SERVICE wikibase:label {
    bd:serviceParam wikibase:language "en".
  }
}
GROUP BY ?place ?placeLabel ?coord ?image ?countryLabel ?article
ORDER BY DESC(?sitelinks)
LIMIT %s
OFFSET %s
"""

HEADERS = {
    "User-Agent": "GlobalPOIBuilder/1.0 (akshaysodhi422@gmail.com)"
}

# ── Balance config ────────────────────────────────────────────────────────────

# Hard cap: no country can have more than this many POIs in TOTAL across all categories
MAX_POIS_PER_COUNTRY = 100

# Per-category per-country caps.
# Concentrated categories (landmarks, castles) need a higher allowance because
# a handful of countries genuinely have many more of them.
# Spread categories (volcanoes, rivers) stay low.
# Rule of thumb: target / 25 categories = ~4 baseline; adjust up for concentrated ones.
CATEGORY_COUNTRY_CAPS = {
    "airports":             4,
    "peaks":                4,
    "volcanoes":            3,
    "deserts":              5,
    "oceans":               2,
    "seas":                 3,
    "rivers":               4,
    "lakes":                4,
    "waterfalls":           4,
    "islands":              6,
    "glaciers":             6,
    "natural":              4,
    "national_parks":       8,
    "cities":              10,
    "landmarks":           15,
    "skyscrapers":         15,
    "bridges":              8,
    "castles":             12,
    "stadiums":             8,
    "universities":        10,
    "museums":             12,
    "infrastructure":       5,
    "space":               10,
    "markets":              5,
    "history_and_mysteries": 15,
}

DEFAULT_CATEGORY_COUNTRY_CAP = 4   # fallback for any category not listed above

# SPARQL page size
FETCH_LIMIT = 200

# Polite delay between SPARQL requests (seconds)
REQUEST_DELAY = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

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
                wait = 5 * (attempt + 1)
                print(f"    Server error {response.status_code}. Retrying in {wait}s...")
                sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            wait = 5 * (attempt + 1)
            print(f"    Request failed: {e}. Retrying in {wait}s...")
            sleep(wait)
    raise Exception("Failed after retries")


def parse_results(data, category):
    rows = []
    for item in data["results"]["bindings"]:
        image_url = item.get("image", {}).get("value")
        if not image_url:
            continue
        country = item.get("countryLabel", {}).get("value") or "Unknown"
        # Skip Wikidata internal IDs surfacing as country names (e.g. "Q12345")
        if country.startswith("Q") and country[1:].isdigit():
            country = "Unknown"
        rows.append({
            "wikidata_id":   item.get("place", {}).get("value", "").split("/")[-1],
            "name":          item.get("placeLabel", {}).get("value"),
            "category":      category,
            "coordinates":   item.get("coord", {}).get("value"),
            "image_url":     image_url,
            "country":       country,
            "wikipedia_url": item.get("article", {}).get("value"),
            "sitelinks":     int(item.get("sitelinks", {}).get("value", 0)),
        })
    return rows


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    with open("config/categories.json", "r", encoding="utf-8") as f:
        categories = json.load(f)

    with open("config/targets.json", "r", encoding="utf-8") as f:
        targets = json.load(f)

    # Only consider categories with a non-zero target
    active_categories = [c for c in categories if targets.get(c, 0) > 0]

    print(f"Active categories    : {len(active_categories)}")
    print(f"Max POIs per country : {MAX_POIS_PER_COUNTRY}  (total across all categories)")
    print(f"\n  Per-category/country caps:")
    for cat in active_categories:
        cap = CATEGORY_COUNTRY_CAPS.get(cat, DEFAULT_CATEGORY_COUNTRY_CAP)
        print(f"    {cat:<30} {cap}")
    print()

    all_rows = []

    # Shared counters across all categories
    country_total    = defaultdict(int)                        # total per country
    country_category = defaultdict(lambda: defaultdict(int))   # per country per category
    seen_ids         = set()                                   # global wikidata_id dedup

    for category in active_categories:
        qid          = categories[category]
        target_count = targets[category]

        print(f"\n{'='*60}")
        print(f"  {category.upper()}  |  global target: {target_count}")
        print(f"{'='*60}")

        offset            = 0
        collected         = 0
        empty_page_streak = 0

        while collected < target_count:
            query = QUERY_TEMPLATE % (qid, FETCH_LIMIT, offset)

            try:
                data = run_query(query)
                rows = parse_results(data, category)
            except Exception as e:
                print(f"  ERROR at offset {offset}: {e}. Skipping category.")
                break

            if not rows:
                empty_page_streak += 1
                if empty_page_streak >= 2:
                    print(f"  No more results. Stopping at {collected}/{target_count}.")
                    break
                offset += FETCH_LIMIT
                sleep(REQUEST_DELAY)
                continue

            empty_page_streak  = 0
            accepted_this_page = 0

            for row in rows:
                wid     = row["wikidata_id"]
                country = row["country"]

                # Gate 1: skip globally seen wikidata IDs
                # (same place returned for multiple historical countries)
                if wid in seen_ids:
                    continue

                # Gate 2: skip if country has hit its TOTAL 100-POI cap
                if country_total[country] >= MAX_POIS_PER_COUNTRY:
                    continue

                # Gate 3: skip if country has hit its per-category cap
                cat_cap = CATEGORY_COUNTRY_CAPS.get(category, DEFAULT_CATEGORY_COUNTRY_CAP)
                if country_category[country][category] >= cat_cap:
                    continue

                # ✓ Accept
                seen_ids.add(wid)
                country_total[country]             += 1
                country_category[country][category] += 1
                all_rows.append(row)
                collected          += 1
                accepted_this_page += 1

                if collected >= target_count:
                    break

            print(f"  offset {offset:>6} | page: {len(rows):>3} | "
                  f"accepted: {accepted_this_page:>3} | "
                  f"category total: {collected}/{target_count}")

            offset += FETCH_LIMIT
            sleep(REQUEST_DELAY)

        # Country breakdown for this category
        cat_rows   = [r for r in all_rows if r["category"] == category]
        by_country = defaultdict(int)
        for r in cat_rows:
            by_country[r["country"]] += 1
        top = sorted(by_country.items(), key=lambda x: -x[1])[:10]
        print(f"\n  Top countries for {category}:")
        for c, n in top:
            print(f"    {c:<35} {n:>3}")

    # ── Save ──────────────────────────────────────────────────────────────────
    df = pd.DataFrame(all_rows)
    df = df[df["image_url"].notna()]

    Path("data/raw").mkdir(parents=True, exist_ok=True)
    output = "data/raw/wikidata_pois_images_only.csv"
    df.to_csv(output, index=False)

    # ── Final report ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  DONE  |  {len(df):,} total POIs  |  "
          f"{df['country'].nunique()} countries")
    print(f"{'='*60}")

    print(f"\n  Per-category totals:")
    for cat, grp in df.groupby("category"):
        print(f"    {cat:<30} {len(grp):>5}  ({grp['country'].nunique()} countries)")

    print(f"\n  Countries with most POIs (top 20):")
    top_countries = df["country"].value_counts().head(20)
    for country, n in top_countries.items():
        bar = "█" * (n // 2)
        print(f"    {country:<35} {n:>4}  {bar}")

    print(f"\n  Saved: {output}")


if __name__ == "__main__":
    main()
