import os
import time
import random
import pandas as pd
from pathlib import Path
from google import genai

INPUT_FILE = "data/processed/pois_scored.csv"
OUTPUT_FILE = "data/processed/pois_final.csv"
CHECKPOINT_FILE = "data/processed/pois_final_checkpoint.csv"

# USE A MODEL THAT WORKS FOR YOU (change if needed)
MODEL_NAME = "models/gemini-2.5-computer-use-preview-10-2025"

BASE_SLEEP = 13.0          # normal delay between requests
SAVE_EVERY = 25           # save checkpoint every N rows
MAX_RETRIES = 8           # retry attempts on rate limit


def build_prompt(row) -> str:
    name = row.get("name", "")
    category = str(row.get("category", "")).replace("_", " ")
    country = row.get("country", "")
    wiki_url = row.get("wikipedia_url", "")

    return f"""
Write a rich, engaging travel-style description of this place in exactly 5 to 6 lines.

Name: {name}
Category: {category}
Country: {country}
Wikipedia URL: {wiki_url}

Rules:
- Output MUST be exactly 5 to 6 lines.
- Each line must be a complete sentence.
- Explain what the place is and why it is notable.
- Do NOT invent specific facts like dates, population, heights, or historical events.
- Do NOT mention Wikidata, AI, datasets, or that you are generating text.
- Keep it natural, informative, and readable.
"""


def clean_lines(text: str) -> list[str]:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]

    cleaned = []
    for ln in lines:
        ln = ln.lstrip("-•* ").strip()
        if ln:
            cleaned.append(ln)

    return cleaned


def enforce_5_to_6_lines(lines: list[str], name: str, country: str) -> str:
    if len(lines) > 6:
        lines = lines[:6]

    while len(lines) < 5:
        lines.append(f"{name} is a notable place located in {country}.")

    return "\n".join(lines)


def generate_with_retry(client, prompt: str):
    delay = BASE_SLEEP

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt
            )
            return resp.text

        except Exception as e:
            msg = str(e).lower()

            # Rate limit handling
            if "429" in msg or "rate" in msg or "quota" in msg or "resource exhausted" in msg:
                wait_time = delay + random.uniform(0, 2)
                print(f"Rate limited. Waiting {wait_time:.1f}s (attempt {attempt+1}/{MAX_RETRIES})")
                time.sleep(wait_time)
                delay *= 2
                continue

            # Other error: stop retrying
            raise e

    raise Exception("Max retries reached due to rate limiting.")


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY environment variable")

    client = genai.Client(api_key=api_key)

    df = pd.read_csv(INPUT_FILE)

    if "description" not in df.columns:
        df["description"] = ""

    # Resume checkpoint if exists
    if Path(CHECKPOINT_FILE).exists():
        checkpoint_df = pd.read_csv(CHECKPOINT_FILE)
        if len(checkpoint_df) == len(df) and "description" in checkpoint_df.columns:
            df = checkpoint_df
            print("Resuming from checkpoint...")

    total = len(df)

    for i, row in df.iterrows():
        existing = str(row.get("description", "")).strip().lower()

        # Only regenerate empty OR old generic ones
        if existing != "" and "is a famous" not in existing:
            continue

        prompt = build_prompt(row)

        try:
            raw_text = generate_with_retry(client, prompt).strip()

            lines = clean_lines(raw_text)

            final_text = enforce_5_to_6_lines(
                lines,
                name=row.get("name", "This place"),
                country=row.get("country", "this country")
            )

            df.at[i, "description"] = final_text

        except Exception as e:
            print(f"Error at row {i}: {e}")
            df.at[i, "description"] = ""

        # Progress
        if i % 10 == 0:
            print(f"Processed {i}/{total}")

        # Save checkpoint
        if i % SAVE_EVERY == 0 and i != 0:
            df.to_csv(CHECKPOINT_FILE, index=False, encoding="utf-8")
            print(f"Checkpoint saved: {CHECKPOINT_FILE}")

        # Normal sleep (extra jitter helps avoid bans)
        time.sleep(BASE_SLEEP + random.uniform(0, 2))

    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    df.to_csv(CHECKPOINT_FILE, index=False, encoding="utf-8")

    print(f"Saved FINAL: {OUTPUT_FILE}")
    print(f"Saved CHECKPOINT: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    main()