import pandas as pd
import re


def parse_point(value):
    if pd.isna(value):
        return None, None

    match = re.search(r"Point\(([-0-9.]+) ([-0-9.]+)\)", str(value))
    if match:
        lon = float(match.group(1))
        lat = float(match.group(2))
        return lat, lon

    return None, None


def main():
    df = pd.read_csv("data/raw/wikidata_pois_images_only.csv")

    coords = df["coordinates"].apply(parse_point)

    df["latitude"] = coords.apply(lambda x: x[0])
    df["longitude"] = coords.apply(lambda x: x[1])

    df.drop(columns=["coordinates"], inplace=True)

    df.to_csv("data/processed/pois_coordinates.csv", index=False)

    print("Coordinates parsed")


if __name__ == "__main__":
    main()