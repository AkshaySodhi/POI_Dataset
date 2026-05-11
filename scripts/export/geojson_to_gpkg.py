import geopandas as gpd
from pathlib import Path


def main():
    input_file = "data/exports/pois.geojson"
    output_file = "data/exports/global_pois.gpkg"

    Path("data/exports").mkdir(parents=True, exist_ok=True)

    gdf = gpd.read_file(input_file)

    # Save into GeoPackage
    gdf.to_file(output_file, layer="pois", driver="GPKG")

    print(f"GeoPackage created: {output_file}")
    print("Total features:", len(gdf))


if __name__ == "__main__":
    main()