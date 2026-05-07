import os
import json
import logging
import time
import vertexai
from vertexai.generative_models import GenerativeModel
from google.api_core import exceptions
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def normalize_hometown_string(hometown: str) -> str:
    """
    Standardizes the hometown string to 'City, State' with Title Case.
    """
    if not hometown or hometown.lower() == 'null':
        return None
    
    # Split by comma, strip whitespace, title case parts, and rejoin
    parts = [p.strip() for p in hometown.split(',')]
    if len(parts) >= 2:
        city = parts[0].title()
        state = parts[1].title()
        return f"{city}, {state}"
    
    return hometown.strip().title()

def get_hometown_via_gemini(athlete_name: str, sport: str, model: GenerativeModel) -> str:
    """
    Queries Gemini to find the hometown of a specific athlete.
    Handles 429 (Too Many Requests) errors with exponential backoff.
    """
    prompt = (
        f"Identify the official hometown (City, State) of the Team USA athlete: {athlete_name}. "
        f"Sport: {sport}. "
        "Return ONLY the 'City, State' string using the full state name (e.g., 'Boulder, Colorado'). If the hometown is unknown, return 'null'."
    )

    max_retries = 5
    wait_time = 5  # Initial wait time in seconds

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            return normalize_hometown_string(text)
        except exceptions.ResourceExhausted:
            if attempt < max_retries - 1:
                logging.warning(f"Quota exceeded (429) for {athlete_name}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
                wait_time *= 2
            else:
                logging.error(f"Max retries reached for {athlete_name} due to quota exhaustion.")
        except Exception as e:
            logging.error(f"Error calling Gemini for {athlete_name}: {e}")
            return None
    return None

def main():
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable not set.")

    # Initialize Vertex AI
    vertexai.init(project=PROJECT)
    # Using gemini-2.5-flash-lite per project requirements
    model = GenerativeModel("gemini-2.5-flash-lite")

    # Paths relative to this script
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "resources", "output")

    if not os.path.exists(OUTPUT_DIR):
        logging.error(f"Directory not found: {OUTPUT_DIR}")
        return

    json_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')]
    
    for filename in json_files:
        filepath = os.path.join(OUTPUT_DIR, filename)
        logging.info(f"Enriching {filename}...")

        with open(filepath, 'r', encoding='utf-8') as f:
            athletes = json.load(f)

        updated_count = 0
        for athlete in athletes:
            hometown_val = athlete.get('hometown')
            # Only query if hometown is missing or explicitly 'null' string
            if not hometown_val or str(hometown_val).lower() == 'null':
                name = athlete.get('name')
                sport = athlete.get('sport')
                hometown = get_hometown_via_gemini(name, sport, model)
                if hometown:
                    athlete['hometown'] = hometown
                    updated_count += 1
                    logging.info(f"Found location for {name}: {hometown}")

        if updated_count > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(athletes, f, indent=4)
            logging.info(f"Updated {updated_count} records in {filename}")

if __name__ == "__main__":
    main()