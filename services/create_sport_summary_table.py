import os
import logging
import sys
import json
from collections import defaultdict
from google.cloud import bigquery
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def create_sport_summary_table():
    """
    Creates a BigQuery table summarizing sports data, including hubs and total Olympians per sport.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    dataset_id = "team_usa_data"
    source_table_id = "regional_hubs_summary"
    target_table_id = "sport_summary"

    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    bq_client = bigquery.Client(project=project_id)

    # --- NEW: Preserve existing sport images ---
    existing_images = {}
    try:
        existing_query = f"SELECT sport_name, sport_image FROM `{project_id}.{dataset_id}.{target_table_id}` WHERE sport_image IS NOT NULL"
        results = bq_client.query(existing_query).result()
        for row in results:
            existing_images[row.sport_name] = row.sport_image
        logging.info(f"Loaded {len(existing_images)} existing sport images for preservation.")
    except Exception:
        logging.info("No existing sport_summary table found. Starting fresh.")

    logging.info(f"Fetching data from {project_id}.{dataset_id}.{source_table_id}...")

    # Query to unnest the sports array and get individual sport entries per hub
    query = f"""
        SELECT
            t1.hometown_id,
            t1.hometown,
            t2.sport AS sport_name,
            t2.count AS athlete_count_in_hub
        FROM
            `{project_id}.{dataset_id}.{source_table_id}` AS t1,
            UNNEST(t1.sports) AS t2
        WHERE t1.sports IS NOT NULL AND ARRAY_LENGTH(t1.sports) > 0
    """

    try:
        query_job = bq_client.query(query)
        results = query_job.result()
    except Exception as e:
        logging.error(f"Failed to query BigQuery: {e}")
        return

    # Aggregate data in Python
    sport_data = defaultdict(lambda: {"total_olympians_for_sport": 0, "hubs": []})

    for row in results:
        sport_name = row.sport_name
        hometown_id = row.hometown_id
        athlete_count_in_hub = row.athlete_count_in_hub

        sport_data[sport_name]["total_olympians_for_sport"] += athlete_count_in_hub
        sport_data[sport_name]["hubs"].append({
            "hometown_id": hometown_id,
            "athlete_count_in_hub": athlete_count_in_hub
        })

    if not sport_data:
        logging.warning("No sport data found to create the summary table.")
        return

    # Prepare data for BigQuery load
    rows_to_insert = []
    for sport_name, data in sport_data.items():
        rows_to_insert.append({
            "sport_name": sport_name,
            "total_olympians_for_sport": data["total_olympians_for_sport"],
            "hubs": data["hubs"],
            "sport_image": existing_images.get(sport_name) # Preserve URL
        })

    # Define the schema for the new table
    schema = [
        bigquery.SchemaField("sport_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("total_olympians_for_sport", "INTEGER", mode="REQUIRED"),
        bigquery.SchemaField("sport_image", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("hubs", "RECORD", mode="REPEATED", fields=[
            bigquery.SchemaField("hometown_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("athlete_count_in_hub", "INTEGER", mode="REQUIRED"),
        ]),
    ]

    target_table_ref = f"{project_id}.{dataset_id}.{target_table_id}"
    logging.info(f"Creating/updating table {target_table_ref} with {len(rows_to_insert)} rows...")

    # Delete the table first to ensure the new schema is applied correctly
    bq_client.delete_table(target_table_ref, not_found_ok=True)

    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition="WRITE_TRUNCATE", # Overwrite the table if it exists
    )
    
    try:
        load_job = bq_client.load_table_from_json(
            rows_to_insert,
            target_table_ref,
            job_config=job_config
        )
        load_job.result()  # Wait for the job to complete
        logging.info(f"Successfully created/updated table {target_table_ref}.")
    except Exception as e:
        logging.error(f"Failed to load data into BigQuery table {target_table_ref}: {e}")

if __name__ == "__main__":
    create_sport_summary_table()