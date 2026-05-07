import os
import json
import re
import logging
import shutil
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
import vertexai
from vertexai.generative_models import GenerativeModel
from dotenv import load_dotenv

# Load environment variables from .env file at the start of the script
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def generate_nil_safe_id(athlete: dict, seen_ids: set) -> str:
    """
    Generates an NIL-safe identifier: <Sport Initial>-<First Initial>-<Last Initial>-<Year First Competed>-<Appearance Count>.
    Handles duplicates by appending a counter.
    """
    name = athlete.get('name') or "Unknown"
    sport = athlete.get('sport') or "Unknown"
    years = athlete.get('participation_years') or []

    # 1. Sport Initial
    sport_initial = sport[0].upper() if sport else "U"

    # 2. Extract Initials (First and Last)
    name_parts = re.sub(r'[^a-zA-Z\s]', '', name).split()
    first_init = name_parts[0][0].upper() if len(name_parts) > 0 else "U"
    last_init = name_parts[-1][0].upper() if len(name_parts) > 1 else "U"

    # 3. Extract Count of appearances and year first appeared
    found_years = []
    for y_str in years:
        found_years.extend([int(y) for y in re.findall(r'\d{4}', str(y_str))])

    appearance_count = len(found_years)
    first_year = min(found_years) if found_years else "0000"

    base_id = f"{sport_initial}-{first_init}-{last_init}-{first_year}-{appearance_count}"
    final_id = base_id
    counter = 1
    while final_id in seen_ids:
        counter += 1
        final_id = f"{base_id}-{counter}"
    
    seen_ids.add(final_id)
    return final_id

def ingest_hometown_data(project_id: str, dataset_id: str, olympians_data: list, update_file_path: str = None, location: str = "US"):
    """
    Demonstrates populating the Hometown Heroes database with enriched,
    aggregated athlete data.

    Args:
        project_id: The Google Cloud project ID.
        dataset_id: The BigQuery dataset ID.
        olympians_data: A list of dictionaries, where each dict represents an Olympian
                        with at least 'name', 'hometown', and 'sport'.
        update_file_path: Optional path to update the source JSON with crawled hometowns.
        location: The geographic location for the dataset (e.g., 'US' or 'EU').
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.athlete_locations"

    # Define the schema once for table creation and streaming verification
    schema = [
        bigquery.SchemaField("athlete_id", "STRING"),
        bigquery.SchemaField("sport", "STRING"),
        bigquery.SchemaField("hometown", "STRING"),
        bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
    ]

    # 1. Fetch existing IDs from BigQuery to enable resumption
    existing_ids = set()
    try:
        query_job = client.query(f"SELECT athlete_id FROM `{table_ref}`")
        results = query_job.result()
        existing_ids = {row.athlete_id for row in results}
        logging.info(f"Found {len(existing_ids)} existing records in BigQuery table. Resuming...")
    except Exception:
        logging.info("Target table not found or empty. Starting fresh.")

    # Initialize Vertex AI once for the duration of the ingestion process
    try:
        vertexai.init(project=project_id)
    except Exception as e:
        logging.warning(f"Failed to initialize Vertex AI: {e}")

    # Ensure the dataset exists
    dataset_ref = client.dataset(dataset_id)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = location
        client.create_dataset(dataset)
        logging.info(f"Created new dataset: {dataset_id}")

    # Streaming inserts require the table to exist beforehand
    try:
        client.get_table(table_ref)
    except NotFound:
        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table)
        logging.info(f"Created table: {table_ref}")

    # 2. Process each athlete: ID generation and Crawling (only for new records)
    updated = False
    # Initialize seen_ids with existing IDs to avoid collisions when generating new ones
    seen_ids = set(existing_ids)
    batch_size = 25
    batch_to_insert = []
    
    for athlete in olympians_data:
        # a. Generate NIL-Safe ID first to check for existence
        # Note: If this is a repeat athlete, generate_nil_safe_id will yield the same ID
        athlete['athlete_id'] = generate_nil_safe_id(athlete, seen_ids)
        
        if athlete['athlete_id'] in existing_ids:
            continue

        athlete_name = athlete.get('name')
        # We now defer hometown enrichment to BigQuery ML using ML.GENERATE_TEXT
        
        # 3. Batching Streaming Inserts for better performance
        row_to_insert = {
            "athlete_id": athlete['athlete_id'],
            "sport": athlete['sport'],
            "hometown": athlete.get('hometown'),
            "load_timestamp": pd.Timestamp.now(tz='UTC').isoformat()
        }
        batch_to_insert.append(row_to_insert)

        if len(batch_to_insert) >= batch_size:
            errors = client.insert_rows_json(table_ref, batch_to_insert)
            if errors:
                logging.error(f"Failed to insert batch: {errors}")
            else:
                logging.info(f"Successfully inserted batch of {len(batch_to_insert)} athletes into BigQuery.")
            batch_to_insert = []

    # Insert any remaining athletes in the last batch
    if batch_to_insert:
        errors = client.insert_rows_json(table_ref, batch_to_insert)
        if errors:
            logging.error(f"Failed to insert final batch: {errors}")
        else:
            logging.info(f"Successfully inserted final batch of {len(batch_to_insert)} athletes.")

    if updated and update_file_path:
        with open(update_file_path, 'w', encoding='utf-8') as f:
            json.dump(olympians_data, f, indent=4)
        logging.info(f"Local JSON file '{update_file_path}' has been updated with new location data.")

    logging.info("Ingestion process completed.")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set. Please set it to your Google Cloud Project ID.")

    # Example: Processing a specific JSON file from the parser output
    # Updated to look for the provided Table Tennis sample or fallback to Baseball
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "resources", "output")
    PROCESSED_DIR = os.path.join(SCRIPT_DIR, "resources", "processed")

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    json_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')]
    
    if json_files:
        for json_file in json_files:
            target_file = os.path.join(OUTPUT_DIR, json_file)
            logging.info(f"Processing {target_file}...")
            with open(target_file, "r", encoding="utf-8") as f:
                athletes = json.load(f)
            ingest_hometown_data(PROJECT, "team_usa_data", athletes, update_file_path=target_file)
            shutil.move(target_file, os.path.join(PROCESSED_DIR, json_file))
            logging.info(f"Successfully moved {json_file} to {PROCESSED_DIR}")
    else:
        print(f"No JSON files found in {OUTPUT_DIR}")