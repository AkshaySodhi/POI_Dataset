import pandas as pd
from sqlalchemy import create_engine

# CHANGE password if needed
DATABASE_URL = "postgresql://postgres:admin@localhost:5432/global_pois"


def main():
    df = pd.read_csv("data/processed/pois_scored.csv")

    engine = create_engine(DATABASE_URL)

    df.to_sql(
        "pois",
        engine,
        if_exists="append",
        index=False
    )

    print("Loaded into PostgreSQL successfully")
    print("Rows inserted:", len(df))


if __name__ == "__main__":
    main()