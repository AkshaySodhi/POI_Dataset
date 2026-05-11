import pandas as pd


def score(row):
    """
    Popularity score out of 100.

    Primary signal: sitelinks (number of Wikipedia language editions).
      - Taj Mahal:        ~130 sitelinks → score near 100
      - Pyramids of Giza: ~120 sitelinks → score near 100
      - Regional landmark:  ~15 sitelinks → score ~55
      - Obscure place:       ~3 sitelinks → score ~35

    Secondary signals: wikipedia link, image, name length.
    """
    score = 0

    # Sitelinks: up to 70 points, scaled at ~1pt per 2 sitelinks, capped at 70
    sitelinks = int(row.get("sitelinks") or 0)
    score += min(70, sitelinks // 2)

    # Has English Wikipedia article: +15
    if pd.notna(row.get("wikipedia_url")):
        score += 15

    # Has image (should always be true given our fetch filter): +10
    if pd.notna(row.get("image_url")):
        score += 10

    # Name length > 6 chars (filters out "Lake X", "Q12345" junk): +5
    if len(str(row.get("name", ""))) > 6:
        score += 5

    return min(score, 100)


def main():
    df = pd.read_csv("data/processed/pois_descriptions.csv")

    # Ensure sitelinks column exists (0 if missing for older data)
    if "sitelinks" not in df.columns:
        df["sitelinks"] = 0

    df["popularity_score"] = df.apply(score, axis=1)

    df = df.sort_values("popularity_score", ascending=False)

    df.to_csv("data/processed/pois_scored.csv", index=False)

    print("Popularity scoring complete")
    print(f"Rows: {len(df)}")
    print(f"\nTop 10 by popularity:")
    print(df[["name", "country", "category", "sitelinks", "popularity_score"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
