import os
from google import genai

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=api_key)

    models = client.models.list()

    for m in models:
        print(m.name)

if __name__ == "__main__":
    main()