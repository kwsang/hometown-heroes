import os
import json
import re
import logging
import shutil
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from dotenv import load_dotenv

# Load environment variables from .env file at the start of the script
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def generate_nil_safe_id(athlete: dict) -> str:
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
    # Normalize years to a list for processing, handles both string "2004, 2008" and list [2004, 2008] formats
    if isinstance(years, str):
        found_years = [int(y) for y in re.findall(r'\d{4}', years)]
    elif isinstance(years, list):
        for y_item in years:
            found_years.extend([int(y) for y in re.findall(r'\d{4}', str(y_item))])

    appearance_count = len(found_years)
    first_year = min(found_years) if found_years else "0000"

    base_id = f"{sport_initial}-{first_init}-{last_init}-{first_year}-{appearance_count}"
    return base_id

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
    table_ref = f"{project_id}.{dataset_id}.athletes_raw"

    # Define the schema once for table creation and streaming verification
    schema = [
        bigquery.SchemaField("athlete_id", "STRING"),
        bigquery.SchemaField("athlete_name", "STRING"), # Added for Gemini enrichment context
        bigquery.SchemaField("sport", "STRING"),
        bigquery.SchemaField("hometown", "STRING"),
        bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
    ]

    # Ensure the dataset exists
    dataset_ref = client.dataset(dataset_id)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = location
        client.create_dataset(dataset)
        logging.info(f"Created new dataset: {dataset_id}")

    # 2. Process each athlete: ID generation
    newly_processed_athletes = [] # Initialize the list here
    for athlete in olympians_data:
        # a. Generate NIL-Safe ID first to check for existence
        # Note: If this is a repeat athlete, generate_nil_safe_id will yield the same ID
        athlete['athlete_id'] = generate_nil_safe_id(athlete)

        athlete_name = athlete.get('name')
        # We now defer hometown enrichment to BigQuery ML using ML.GENERATE_TEXT
        
        # 3. Batching Streaming Inserts for better performance
        row_to_insert = {
            "athlete_id": athlete['athlete_id'],
            "athlete_name": athlete.get('name'), # Temporary context for BQML
            "sport": athlete['sport'],
            "hometown": athlete.get('hometown'),
            "load_timestamp": pd.Timestamp.now(tz='UTC')
        }
        newly_processed_athletes.append(row_to_insert)

    # 4. Perform a Batch Load for the current JSON file
    # Batch loads bypass the streaming buffer, allowing immediate DML (UPDATEs)
    if newly_processed_athletes:
        df_new = pd.DataFrame(newly_processed_athletes)
        job_config = bigquery.LoadJobConfig(
            schema=schema,
            write_disposition="WRITE_APPEND",
        )

        logging.info(f"Loading {len(df_new)} records into staging table {table_ref}...")
        job = client.load_table_from_dataframe(df_new, table_ref, job_config=job_config)
        job.result()  # Wait for the load to complete
        logging.info(f"Successfully loaded {len(df_new)} athletes.")
    else:
        logging.info("No new athletes found in this file to ingest.")

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