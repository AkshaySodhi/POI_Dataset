import json
import requests
import pandas as pd
from pathlib import Path
from time import sleep

SPARQL_URL = "https://query.wikidata.org/sparql"

# NOTE: We now REQUIRE image (?place wdt:P18 ?image.)
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


def run_query(query: str, retries: int = 6):
    """
    Runs a SPARQL query against Wikidata with retry logic.
    Handles 500/502/503/504 and 429 rate-limit errors.
    """
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
                print(f"Server error {response.status_code}. Retrying in {wait_time}s...")
                sleep(wait_time)
                continue

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            wait_time = 5 * (attempt + 1)
            print(f"Request failed: {e}. Retrying in {wait_time}s...")
            sleep(wait_time)

    raise Exception("Failed after retries")


def parse_results(data, category):
    rows = []
    for item in data["results"]["bindings"]:
        image_url = item.get("image", {}).get("value")

        # Extra safety check (should always exist due to query filter)
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


def main():
    # Load category QIDs
    with open("config/categories.json", "r", encoding="utf-8") as f:
        categories = json.load(f)

    # Load target distribution counts
    with open("config/targets.json", "r", encoding="utf-8") as f:
        targets = json.load(f)

    all_rows = []

    # Smaller limit = fewer server crashes
    limit = 200

    for category, qid in categories.items():
        target_count = targets.get(category, 0)

        if target_count == 0:
            print(f"Skipping {category} (no target count set)")
            continue

        print(f"\n========== Fetching {category} (target {target_count}) ==========")

        offset = 0
        collected = 0

        while collected < target_count:
            query = QUERY_TEMPLATE % (qid, limit, offset)

            try:
                data = run_query(query)
                rows = parse_results(data, category)

                if not rows:
                    print(f"{category}: No more results available. Stopping early.")
                    break

                needed = target_count - collected
                rows_to_add = rows[:needed]

                all_rows.extend(rows_to_add)
                collected += len(rows_to_add)

                print(f"{category}: collected {collected}/{target_count} (offset={offset})")

                offset += limit
                sleep(4)

            except Exception as e:
                print(f"ERROR in {category} at offset {offset}: {e}")
                print("Skipping this category...")
                break

    df = pd.DataFrame(all_rows)

    # Final safety cleanup (remove any empty image_url)
    df = df[df["image_url"].notna()]

    Path("data/raw").mkdir(parents=True, exist_ok=True)
    output = "data/raw/wikidata_pois_images_only.csv"
    df.to_csv(output, index=False)

    print("\n================ DONE ================")
    print(f"Saved: {output}")
    print(f"Total rows collected: {len(df)}")


if __name__ == "__main__":
    main()