import os
import logging
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def check_model_connection():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable not set.")
        return

    client = bigquery.Client(project=project_id)
    dataset_id = "team_usa_data"
    model_name = "gemini_hometown_model"
    
    test_query = f"""
    SELECT JSON_VALUE(ml_generate_text_result, '$.candidates[0].content.parts[0].text') as response_text
    FROM ML.GENERATE_TEXT(
      MODEL `{project_id}.{dataset_id}.{model_name}`,
      (SELECT 'Verify connection' AS prompt),
      STRUCT(0.1 AS temperature, 10 AS max_output_tokens)
    )
    """
    
    logging.info(f"Testing connection to model: {project_id}.{dataset_id}.{model_name}")
    
    try:
        query_job = client.query(test_query)
        results = list(query_job.result())
        
        if results:
            logging.info("SUCCESS: BigQuery is successfully communicating with Gemini.")
            logging.info(f"Gemini response: {results[0].response_text}")
    except Exception as e:
        logging.error("FAILURE: Connection check failed.")
        logging.error(f"Error details: {e}")
        logging.info("Check: 1. Service Account Permissions, 2. Connection Region, 3. Model Name.")

if __name__ == "__main__":
    check_model_connection()