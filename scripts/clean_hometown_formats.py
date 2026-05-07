import os
import json
import re
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# The regex to validate "City, State" format, allowing accented characters and common punctuation
HOMETOWN_REGEX = r'^[a-zA-ZÀ-ÿ\s\.\-\']{2,50},\s[a-zA-ZÀ-ÿ\s\.\-\']{2,50}$'

def clean_and_validate_hometown(hometown_str: str) -> str or None:
    """
    Removes surrounding double quotes from a hometown string if present,
    then validates it against the HOMETOWN_REGEX. Returns the cleaned/validated
    string or None if invalid.
    """
    if not isinstance(hometown_str, str):
        return None

    cleaned_hometown = hometown_str.strip()

    # Remove surrounding double quotes if they exist
    if cleaned_hometown.startswith('"') and cleaned_hometown.endswith('"'):
        cleaned_hometown = cleaned_hometown[1:-1].strip()

    # Validate against the strict regex
    if re.match(HOMETOWN_REGEX, cleaned_hometown):
        return cleaned_hometown
    else:
        return None

def clean_hometown_jsons():
    """
    Iterates through JSON files in output and processed folders,
    cleans and validates hometown entries, and updates the files.
    """
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    
    DATA_DIRS = [
        os.path.join(RESOURCES_DIR, "output"),
        os.path.join(RESOURCES_DIR, "processed")
    ]

    for directory in DATA_DIRS:
        if not os.path.exists(directory):
            logging.warning(f"Directory not found, skipping: {directory}")
            continue
            
        logging.info(f"Processing directory: {directory}")
        
        json_files = [f for f in os.listdir(directory) if f.endswith('.json') and not f.startswith('cache_')]

        for filename in json_files:
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    athletes = json.load(f)
                
                if not isinstance(athletes, list):
                    continue

                changed = False
                for athlete in athletes:
                    original_hometown = athlete.get('hometown')
                    new_hometown = clean_and_validate_hometown(original_hometown)
                    if new_hometown != original_hometown:
                        athlete['hometown'] = new_hometown
                        changed = True
                
                if changed:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(athletes, f, indent=4)
                    logging.info(f"Updated hometowns in {filename}")

            except Exception as e:
                logging.error(f"Failed to process {filename}: {e}")

if __name__ == "__main__":
    clean_hometown_jsons()