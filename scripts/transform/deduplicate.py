import pandas as pd


def main():
    df = pd.read_csv("data/processed/pois_coordinates.csv")

    print(f"Rows before cleaning: {len(df)}")

    # Remove rows missing important fields
    df = df.dropna(subset=["name", "latitude", "longitude", "image_url"])

    # --- Fix: deduplicate on wikidata_id first ---
    # A single place (e.g. Nicomedia) can appear many times because Wikidata
    # returns one row per country it belonged to historically.
    # Keep the row whose country looks most "current" by preferring rows
    # that don't contain historical empire names.
    HISTORICAL_COUNTRIES = {
        "Byzantine Empire", "Ottoman Empire", "Ancient Rome", "Roman Empire",
        "Latin Empire", "Seleucid Empire", "Ptolemaic Kingdom", "Empire of Nicaea",
        "Bithynia", "Lycia", "Macedonia", "Rhodes", "Persia", "Achaemenid Empire",
        "Holy Roman Empire", "Habsburg Monarchy", "Soviet Union",
    }

    def country_priority(country):
        """Lower = preferred. Modern countries rank 0, historical empires rank 1."""
        if pd.isna(country):
            return 2
        return 1 if country in HISTORICAL_COUNTRIES else 0

    # Sort so modern countries come first, then deduplicate keeping first per wikidata_id
    if "wikidata_id" in df.columns:
        df["_country_rank"] = df["country"].apply(country_priority)
        df = df.sort_values("_country_rank")
        df = df.drop_duplicates(subset=["wikidata_id"], keep="first")
        df = df.drop(columns=["_country_rank"])
        print(f"Rows after wikidata_id dedup: {len(df)}")

    # Secondary dedup: same name + category in the same country (catches OSM/Wikidata overlaps)
    df = df.drop_duplicates(subset=["name", "country", "category"])
    print(f"Rows after name+country+category dedup: {len(df)}")

    # Reset index
    df = df.reset_index(drop=True)

    df.to_csv("data/processed/pois_clean.csv", index=False)
    print(f"Saved: data/processed/pois_clean.csv")


if __name__ == "__main__":
    main()