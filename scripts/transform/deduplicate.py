import pandas as pd


def main():
    df = pd.read_csv("data/processed/pois_coordinates.csv")

    # Remove rows missing important fields
    df = df.dropna(subset=["name", "country", "latitude", "longitude", "image_url"])

    # Remove duplicates (same name + country + category)
    df = df.drop_duplicates(subset=["name", "country", "category"])

    # Reset index
    df = df.reset_index(drop=True)

    df.to_csv("data/processed/pois_clean.csv", index=False)

    print("Deduplication complete")
    print("Rows after cleaning:", len(df))


if __name__ == "__main__":
    main()