import os
import logging
from google.cloud import bigquery
from google.cloud import firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def delete_all_narratives():
    """
    Deletes all AI-generated narratives from BigQuery and Firestore.
    Used to reset the state for re-generation.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    dataset_id = "team_usa_data"
    
    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    # 1. Clear BigQuery Cache
    logging.info("Clearing narratives from BigQuery...")
    bq_client = bigquery.Client(project=project_id)
    
    # Update query to nullify narrative and timestamp
    clear_bq_query = f"""
        UPDATE `{project_id}.{dataset_id}.regional_hubs_summary`
        SET narrative = NULL,
            narrative_timestamp = NULL
        WHERE narrative IS NOT NULL
    """
    
    try:
        query_job = bq_client.query(clear_bq_query)
        query_job.result()
        logging.info(f"BigQuery update complete. Rows affected: {query_job.num_dml_affected_rows}")
    except Exception as e:
        logging.error(f"Failed to clear BigQuery narratives: {e}")

    # 2. Clear Firestore Serving Layer
    logging.info("Clearing narratives from Firestore...")
    db = firestore.Client(project=project_id)
    collection_ref = db.collection("hubs")
    
    try:
        docs = collection_ref.stream()
        count = 0
        for doc in docs:
            # Check if narrative exists before attempting to delete the field
            if 'narrative' in doc.to_dict():
                doc.reference.update({
                    "narrative": firestore.DELETE_FIELD
                })
                count += 1
        
        logging.info(f"Firestore update complete. Fields removed from {count} documents.")
    except Exception as e:
        logging.error(f"Failed to clear Firestore narratives: {e}")

    logging.info("All narratives have been deleted from the cache and serving layer.")

if __name__ == "__main__":
    delete_all_narratives()