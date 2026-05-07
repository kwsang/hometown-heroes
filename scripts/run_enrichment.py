import os
import logging
import time
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_chunked_enrichment(project_id: str, dataset_id: str, chunk_size: int = 25):
    client = bigquery.Client(project=project_id)
    staging_ref = f"{project_id}.{dataset_id}.athletes_raw"
    production_ref = f"{project_id}.{dataset_id}.athletes"
    model_ref = f"{project_id}.{dataset_id}.gemini_hometown_model"

    # Ensure the production table exists before starting enrichment
    try:
        client.get_table(production_ref)
    except NotFound:
        logging.info(f"Production table {production_ref} not found. Creating...")
        schema = [
            bigquery.SchemaField("athlete_id", "STRING"),
            bigquery.SchemaField("sport", "STRING"),
            bigquery.SchemaField("hometown", "STRING"),
            bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
        ]
        table = bigquery.Table(production_ref, schema=schema)
        # Cluster by athlete_id to make the NOT IN exclusion check highly efficient
        table.clustering_fields = ["athlete_id"]
        client.create_table(table)
        logging.info(f"Successfully created production table: {production_ref}")

    # This script uses an 'Exclusion Pattern' instead of 'Deletion'.
    # It avoids DML on the staging table, preventing streaming buffer conflicts.
    promote_script = f"""
    -- 1. Isolate the chunk to process into a temporary work table
    CREATE OR REPLACE TEMP TABLE current_work_chunk AS
    SELECT 
        athlete_id, 
        athlete_name, 
        sport,
        CONCAT(
            'Identify the official hometown (City, State) of the Team USA athlete: ', 
            athlete_name, 
            '. Sport: ', sport, '. ',
            'Return ONLY the "City, State". If unknown, return "null".'
        ) AS prompt
    FROM `{staging_ref}`
    -- Only pick athletes who haven't been promoted to the production table yet
    WHERE athlete_id NOT IN (SELECT athlete_id FROM `{production_ref}`)
    LIMIT {chunk_size};

    -- 2. Enrich and promote directly to production
    INSERT INTO `{production_ref}` (athlete_id, sport, hometown, load_timestamp)
    SELECT 
        res.athlete_id, 
        res.sport,
        JSON_VALUE(res.ml_generate_text_result, '$.candidates[0].content.parts[0].text') as hometown,
        CURRENT_TIMESTAMP() as load_timestamp
    FROM ML.GENERATE_TEXT(
      MODEL `{model_ref}`,
      TABLE current_work_chunk,
      STRUCT(0.1 AS temperature, 100 AS max_output_tokens)
    ) res;

    -- 3. Return the count for the Python monitor
    SELECT COUNT(*) as processed_count FROM current_work_chunk;
    """

    logging.info(f"Starting enrichment and promotion from {staging_ref} to {production_ref}...")
    
    total_updated = 0
    while True:
        logging.info(f"Processing next chunk of {chunk_size} athletes...")
        query_job = client.query(promote_script)
        results = query_job.result() # Wait for the script to finish
        
        # Get the count from the final SELECT statement in the script
        # This represents how many rows were isolated and processed
        updated_count = next(results).processed_count
        total_updated += updated_count
        
        if updated_count == 0:
            logging.info(f"Finished. Total athletes promoted to production: {total_updated}")
            break
            
        logging.info(f"Successfully promoted {updated_count} rows. Total: {total_updated}")
        time.sleep(2) # Small cooldown between API bursts

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT: raise ValueError("GOOGLE_CLOUD_PROJECT not set.")
    run_chunked_enrichment(PROJECT, "team_usa_data")