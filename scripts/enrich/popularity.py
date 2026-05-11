import pandas as pd


def score(row):
    score = 50

    # Wikipedia link = more important
    if pd.notna(row.get("wikipedia_url")):
        score += 20

    # Image exists (should already)
    if pd.notna(row.get("image_url")):
        score += 20

    # Longer names often mean specific famous places
    if len(str(row.get("name", ""))) > 6:
        score += 10

    return min(score, 100)


def main():
    df = pd.read_csv("data/processed/pois_descriptions.csv")

    df["popularity_score"] = df.apply(score, axis=1)

    df.to_csv("data/processed/pois_scored.csv", index=False)

    print("Popularity scoring complete")
    print("Rows:", len(df))


if __name__ == "__main__":
    main()