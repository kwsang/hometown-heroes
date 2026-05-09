import os
import asyncio
import logging
import sys
import time
from google.api_core import exceptions as google_exceptions
from google.cloud import bigquery
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bigquery_service import BigQueryService
from services.ai_insights_service import AIInsightsService
from services.firestore_service import FirestoreService

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def _process_single_narrative(hub, insights_service, semaphore):
    """Generates a narrative for a hub with retry logic for rate limits."""
    hometown_id = hub.get('id')
    pretty_name = hub.get('pretty_city_name')
    
    async with semaphore:
        max_retries = 3
        retry_wait = 10
        
        for attempt in range(max_retries):
            try:
                # Fetch stats required for prompt
                stats = insights_service.bigquery.get_aggregate_hub_stats(hometown_id)
                elevation = stats[0].get("regional_elevation", "Unknown") if stats else "Unknown"
                climate_mock = {
                    "avg_elevation": f"{elevation}m" if elevation != "Unknown" else elevation,
                    "notable_features": "Local terrain and climate conditions relevant to sport excellence."
                }
                
                # Generate via Gemini (bypassing internal individual DB updates in the service)
                narrative = await insights_service.gemini.generate_hub_narrative(hometown_id, stats, climate_mock)
                return {"hid": hometown_id, "narrative": narrative}

            except google_exceptions.ResourceExhausted:
                if attempt < max_retries - 1:
                    logging.warning(f"Quota exceeded for {pretty_name}. Retrying in {retry_wait}s...")
                    await asyncio.sleep(retry_wait)
                    retry_wait += 10
                else:
                    logging.error(f"Max retries reached for {pretty_name}.")
            except Exception as e:
                logging.error(f"Error processing {pretty_name}: {e}")
                break
    return None

async def generate_hub_narratives():
    """
    Iterates through all regional hubs in BigQuery and triggers the 
    AI narrative generation and caching process using Gemini.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    # Initialize services
    bq_service = BigQueryService(project_id=project_id)
    insights_service = AIInsightsService(project_id=project_id)
    firestore_service = FirestoreService(project_id=project_id)

    logging.info("Retrieving all regional hubs from BigQuery summary table...")
    try:
        hubs = bq_service.get_all_hubs()
    except Exception as e:
        logging.error(f"Failed to fetch hubs from BigQuery: {e}")
        return

    # 1. Identify hubs missing narratives
    hubs_to_process = [h for h in hubs if not h.get('narrative') or h.get('narrative') == ""]
    
    # 2. Identify existing narratives that need to be synced to the Firestore serving layer
    hubs_to_sync = [h for h in hubs if h.get('narrative')]

    if not hubs_to_process:
        logging.info("All hubs already have narratives in BigQuery.")
    else:
        logging.info(f"Processing {len(hubs_to_process)} hubs for AI insight generation...")

    logging.info(f"Checking Firestore synchronization for {len(hubs_to_sync)} existing narratives...")

    # 3. Parallel processing for NEW narratives
    semaphore = asyncio.Semaphore(5) 
    tasks = [_process_single_narrative(hub, insights_service, semaphore) for hub in hubs_to_process]
    
    results = await asyncio.gather(*tasks)
    successful_results = [r for r in results if r]

    # 4. Batch Update BigQuery and Firestore for new results
    if successful_results:
        logging.info(f"Performing batch update for {len(successful_results)} narratives...")
        
        merge_query = f"""
            MERGE `{project_id}.team_usa_data.regional_hubs_summary` T
            USING UNNEST(@updates) S
            ON T.hometown_id = S.hid
            WHEN MATCHED THEN
              UPDATE SET narrative = S.narrative, narrative_timestamp = CURRENT_TIMESTAMP()
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("updates", "RECORD", [
                    bigquery.StructQueryParameter("row",
                        bigquery.ScalarQueryParameter("hid", "STRING", r["hid"]),
                        bigquery.ScalarQueryParameter("narrative", "STRING", r["narrative"])
                    ) for r in successful_results
                ])
            ]
        )
        bq_service.client.query(merge_query, job_config=job_config).result()

        # Update Firestore Serving Layer
        for r in successful_results:
            firestore_service.update_field(r['hid'], "narrative", r['narrative'])

    # 5. Ensure existing BigQuery narratives are present in Firestore
    for h in hubs_to_sync:
        # We always update to ensure the serving layer is fresh, 
        # though we could optimize by checking FS existence first.
        firestore_service.update_field(h['id'], "narrative", h['narrative'])

    logging.info("Hub narrative generation and Firestore synchronization complete.")

if __name__ == "__main__":
    asyncio.run(generate_hub_narratives())