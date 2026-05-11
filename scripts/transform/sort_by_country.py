#!/usr/bin/env python3
"""
Script to sort POIs by country from the descriptions CSV file.
"""

import pandas as pd
import os

def sort_pois_by_country():
    # Define file paths
    input_file = os.path.join('data', 'processed', 'pois_descriptions.csv')
    output_file = os.path.join('data', 'processed', 'pois_descriptions_sorted.csv')

    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file {input_file} does not exist.")
        return

    try:
        # Read the CSV file
        print(f"Reading {input_file}...")
        df = pd.read_csv(input_file)

        # Check if 'country' column exists
        if 'country' not in df.columns:
            print("Error: 'country' column not found in the CSV file.")
            return

        # Sort by country
        print("Sorting by country...")
        df_sorted = df.sort_values(by='country')

        # Write to new file
        print(f"Writing sorted data to {output_file}...")
        df_sorted.to_csv(output_file, index=False)

        print(f"Successfully sorted {len(df_sorted)} entries by country.")
        print(f"Sorted file saved as: {output_file}")

    except Exception as e:
        print(f"Error processing the file: {e}")

if __name__ == "__main__":
    sort_pois_by_country()