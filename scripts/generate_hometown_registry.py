import os
import json
import re
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def generate_hometown_registry():
    """
    Iterates through all sport JSON files in output and processed folders,
    aggregating statistics by hometown.
    """
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    
    # Source directories for sport data
    DATA_DIRS = [
        os.path.join(RESOURCES_DIR, "output"),
        os.path.join(RESOURCES_DIR, "processed")
    ]
    
    registry = {}

    for directory in DATA_DIRS:
        if not os.path.exists(directory):
            logging.warning(f"Directory not found, skipping: {directory}")
            continue
            
        logging.info(f"Processing directory: {directory}")
        
        # Filter for sport JSON files
        json_files = [
            f for f in os.listdir(directory) 
            if f.endswith('.json') and not f.startswith('cache_') and f != 'sport_map.json'
        ]

        for filename in json_files:
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    athletes = json.load(f)
                
                if not isinstance(athletes, list):
                    continue

                for athlete in athletes:
                    hometown = athlete.get('hometown')
                    sport = athlete.get('sport')

                    if not hometown:
                        continue

                    hometown_str = str(hometown).strip()

                    # Ignore placeholders like 'Unknown' or 'Null' and validate 'City, State' format
                    if re.search(r'null|unknown', hometown_str, re.IGNORECASE) or \
                       not re.match(r'^[a-zA-ZÀ-ÿ\s\.\-\']{2,50},\s[a-zA-ZÀ-ÿ\s\.\-\']{2,50}$', hometown_str):
                        continue

                    if hometown not in registry:
                        registry[hometown] = {
                            "total_athletes": 0,
                            "sports": {}
                        }
                    
                    registry[hometown]["total_athletes"] += 1
                    # Increment count for the specific sport in this hometown
                    registry[hometown]["sports"][sport] = registry[hometown]["sports"].get(sport, 0) + 1

            except Exception as e:
                logging.error(f"Failed to process {filename}: {e}")

    # Save the aggregated registry
    output_path = os.path.join(RESOURCES_DIR, "hometown_registry.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=4)
    
    logging.info(f"Successfully generated registry with {len(registry)} unique hometowns at {output_path}")

if __name__ == "__main__":
    generate_hometown_registry()