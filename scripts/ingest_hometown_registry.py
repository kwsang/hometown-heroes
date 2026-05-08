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
    logging.info(f"Processing {len(rows)} hometown records for {table_ref}...")

    # Check if the table exists to determine if we can MERGE or must do an initial LOAD
    try:
        client.get_table(table_ref)
        table_exists = True
    except NotFound:
        table_exists = False

    if not table_exists:
        logging.info("Target table not found. Performing initial load.")
        job_config = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
        client.load_table_from_json(rows, table_ref, job_config=job_config).result()
    else:
        # Perform an UPSERT using a staging table and MERGE statement
        staging_table_ref = f"{table_ref}_staging"
        logging.info(f"Table exists. Performing upsert via staging: {staging_table_ref}")

        staging_config = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
        client.load_table_from_json(rows, staging_table_ref, job_config=staging_config).result()

        merge_query = f"""
            MERGE `{table_ref}` T
            USING `{staging_table_ref}` S
            ON T.hometown = S.hometown
            WHEN MATCHED THEN
              UPDATE SET 
                total_athletes = S.total_athletes,
                sports = S.sports,
                load_timestamp = S.load_timestamp
            WHEN NOT MATCHED THEN
              INSERT (hometown, total_athletes, sports, lat, lng, regional_elevation, hometown_id, region, load_timestamp)
              VALUES (S.hometown, S.total_athletes, S.sports, S.lat, S.lng, S.regional_elevation, S.hometown_id, S.region, S.load_timestamp)
        """
        client.query(merge_query).result()
        client.delete_table(staging_table_ref, not_found_ok=True)

    logging.info(f"Successfully synchronized hometown registry in BigQuery.")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")
    ingest_hometown_registry(PROJECT, "team_usa_data")