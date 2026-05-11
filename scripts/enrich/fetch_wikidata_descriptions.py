import pandas as pd
import requests
from time import sleep

API_URL = "https://www.wikidata.org/w/api.php"


def fetch_descriptions_batch(qids):
    params = {
        "action": "wbgetentities",
        "ids": "|".join(qids),
        "props": "descriptions",
        "languages": "en",
        "format": "json"
    }

    HEADERS = {
        "User-Agent": "GlobalPOIBuilder/1.0 (akshaysodhi422@gmail.com)"
    }

    r = requests.get(API_URL, params=params, headers=HEADERS, timeout=60)

    if r.status_code == 403:
        raise Exception("403 Forbidden: Wikidata blocked request. Slow down or change User-Agent.")

    r.raise_for_status()
    data = r.json()

    results = {}
    entities = data.get("entities", {})

    for qid, entity in entities.items():
        desc = entity.get("descriptions", {}).get("en", {}).get("value")
        results[qid] = desc

    return results


def main():
    df = pd.read_csv("data/processed/pois_clean.csv")

    qids = df["wikidata_id"].dropna().unique().tolist()

    description_map = {}

    batch_size = 50

    for i in range(0, len(qids), batch_size):
        batch = qids[i:i + batch_size]

        try:
            descs = fetch_descriptions_batch(batch)
            description_map.update(descs)

            print(f"Fetched {min(i+batch_size, len(qids))}/{len(qids)} descriptions")

        except Exception as e:
            print("Batch failed:", e)

        sleep(1)

    df["description"] = df["wikidata_id"].map(description_map)

    df.to_csv("data/processed/pois_descriptions.csv", index=False)
    print("Saved: data/processed/pois_descriptions.csv")


if __name__ == "__main__":
    main()