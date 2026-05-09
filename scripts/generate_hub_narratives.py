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
        logging.info(f"  [AI] Starting narrative generation for: {pretty_name}...")
        max_retries = 3
        retry_wait = 10
        
        for attempt in range(max_retries):
            try:
                # Fetch stats required for prompt
                stats = await asyncio.to_thread(insights_service.bigquery.get_aggregate_hub_stats, hometown_id)
                logging.debug(f"    Fetched {len(stats)} sport stats for {pretty_name}")
                
                elevation = stats[0].get("regional_elevation", "Unknown") if stats else "Unknown"
                climate_mock = {
                    "avg_elevation": f"{elevation}m" if elevation != "Unknown" else elevation,
                    "notable_features": "Local terrain and climate conditions relevant to sport excellence."
                }
                
                # Generate via Gemini (bypassing internal individual DB updates in the service)
                narrative = await insights_service.gemini.generate_hub_narrative(hometown_id, stats, climate_mock)
                logging.info(f"  [AI] COMPLETED narrative for: {pretty_name}")
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
    # Throttled to 3 concurrent AI calls to respect RPM limits and avoid thread pool saturation
    semaphore = asyncio.Semaphore(3) 
    tasks = [_process_single_narrative(hub, insights_service, semaphore) for hub in hubs_to_process]
    
    if tasks:
        results = await asyncio.gather(*tasks)
        successful_results = [r for r in results if r]

        # 4. Batch Update BigQuery and Firestore for new results
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
        query_job = bq_service.client.query(merge_query, job_config=job_config)
        await asyncio.to_thread(query_job.result)

        # Update Firestore Serving Layer
        fs_updates = [{"id": r["hid"], "narrative": r["narrative"]} for r in successful_results]
        await asyncio.to_thread(firestore_service.batch_update_fields, fs_updates)

    # 5. Ensure existing BigQuery narratives are present in Firestore
    if hubs_to_sync:
        logging.info(f"Synchronizing {len(hubs_to_sync)} existing narratives to Firestore...")
        fs_sync_updates = [{"id": h["id"], "narrative": h["narrative"]} for h in hubs_to_sync]
        await asyncio.to_thread(firestore_service.batch_update_fields, fs_sync_updates)

    logging.info("Hub narrative generation and Firestore synchronization complete.")

if __name__ == "__main__":
    asyncio.run(generate_hub_narratives())