import pandas as pd
import json

df = pd.read_csv("data/processed/pois_scored.csv")

features = []

for _, row in df.iterrows():
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [
                row["longitude"],
                row["latitude"]
            ]
        },
        "properties": {
            "name": row["name"],
            "category": row["category"],
            "country": row["country"],
            "description": row["description"],
            "image_url": row["image_url"]
        }
    }
    
    features.append(feature)

geojson = {
    "type": "FeatureCollection",
    "features": features
}

with open("data/exports/pois.geojson", "w") as f:
    json.dump(geojson, f)

print("GeoJSON exported")