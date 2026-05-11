import pandas as pd
from sqlalchemy import create_engine
from pathlib import Path

DATABASE_URL = "postgresql+psycopg2://postgres:admin@127.0.0.1:5432/global_pois"

def main():
    engine = create_engine(DATABASE_URL)

    df = pd.read_sql("SELECT * FROM pois", engine)

    Path("data/exports").mkdir(parents=True, exist_ok=True)

    df.to_csv("data/exports/global_pois.csv", index=False)
    print("CSV exported: data/exports/global_pois.csv")

if __name__ == "__main__":
    main()