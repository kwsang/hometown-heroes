import os
import json
import logging
from datetime import datetime
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def ingest_hometown_registry(project_id: str, dataset_id: str):
    """
    Ingests the hometown registry JSON into BigQuery with a repeated record schema.
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.hometown_registry"

    # Define the schema
    schema = [
        bigquery.SchemaField("hometown", "STRING"),
        bigquery.SchemaField("total_athletes", "INTEGER"),
        bigquery.SchemaField("sports", "RECORD", mode="REPEATED", fields=[
            bigquery.SchemaField("sport", "STRING"),
            bigquery.SchemaField("count", "INTEGER"),
        ]),
        bigquery.SchemaField("lat", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("lng", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("regional_elevation", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("hometown_id", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("region", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
    ]

    # Paths
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    REGISTRY_FILE = os.path.join(RESOURCES_DIR, "hometown_registry.json")

    if not os.path.exists(REGISTRY_FILE):
        logging.error(f"Registry file not found: {REGISTRY_FILE}")
        return

    # Ensure the dataset exists
    dataset_ref = client.dataset(dataset_id)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        logging.info(f"Creating dataset: {dataset_id}")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset)

    # 1. Load and Transform Data
    logging.info(f"Reading registry from {REGISTRY_FILE}...")
    with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
        registry_data = json.load(f)

    rows = []
    for hometown, data in registry_data.items():
        # Transform the sports dict into a list of records for BigQuery
        sports_list = [
            {"sport": sport, "count": count} 
            for sport, count in data.get("sports", {}).items()
        ]
        
        rows.append({
            "hometown": hometown,
            "total_athletes": data.get("total_athletes", 0),
            "sports": sports_list,
            "lat": None,  # Will be populated by process_geocoding.py
            "lng": None,  # Will be populated by process_geocoding.py
            "regional_elevation": None,  # Will be populated by process_geocoding.py
            "hometown_id": None,  # Will be populated by process_geocoding.py
            "region": None,  # Will be populated by process_geocoding.py
            "load_timestamp": pd.Timestamp.now(tz='UTC').isoformat(),
        })

    if not rows:
        logging.warning("No data found in registry to ingest.")
        return

    # 2. Ingest into BigQuery
    logging.info(f"Ingesting {len(rows)} hometown records into {table_ref}...")
    
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE", # Replace the registry with the latest aggregation
    )

    job = client.load_table_from_json(rows, table_ref, job_config=job_config)
    job.result()  # Wait for completion

    logging.info(f"Successfully loaded hometown registry into BigQuery.")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")
    ingest_hometown_registry(PROJECT, "team_usa_data")