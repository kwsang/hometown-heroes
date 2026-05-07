import os
import logging
import time
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def run_chunked_enrichment(project_id: str, dataset_id: str, chunk_size: int = 25):
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.athletes"
    model_ref = f"{project_id}.{dataset_id}.gemini_hometown_model"

    enrich_query = f"""
    UPDATE `{table_ref}` a
    SET hometown = JSON_VALUE(res.ml_generate_text_result, '$.candidates[0].content.parts[0].text')
    FROM ML.GENERATE_TEXT(
      MODEL `{model_ref}`,
      (
        SELECT 
          athlete_id, 
          athlete_name,
          CONCAT(
            'Identify the official hometown (City, State) of the Team USA athlete: ', 
            athlete_name, 
            '. Sport: ', sport, '. ',
            'Return ONLY the "City, State". If unknown, return "null".'
          ) AS prompt
        FROM `{table_ref}`
        WHERE (hometown IS NULL OR LOWER(hometown) = 'null' OR hometown = '')
          AND athlete_name IS NOT NULL
        LIMIT {chunk_size}
      ),
      STRUCT(0.1 AS temperature, 100 AS max_output_tokens)
    ) res
    WHERE a.athlete_id = res.athlete_id;
    """

    logging.info(f"Starting chunked enrichment for {table_ref}...")
    
    total_updated = 0
    while True:
        logging.info(f"Processing next chunk of {chunk_size} athletes...")
        query_job = client.query(enrich_query)
        query_job.result() # Wait for the chunk to finish
        
        updated_count = query_job.num_dml_affected_rows
        total_updated += updated_count
        
        if updated_count == 0:
            logging.info(f"Finished. Total athletes enriched: {total_updated}")
            break
            
        logging.info(f"Successfully updated {updated_count} rows in this chunk. Total: {total_updated}")
        time.sleep(2) # Small cooldown between API bursts

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT: raise ValueError("GOOGLE_CLOUD_PROJECT not set.")
    run_chunked_enrichment(PROJECT, "team_usa_data")