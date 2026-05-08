import os
import asyncio
import logging
import sys
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bigquery_service import BigQueryService
from services.ai_insights_service import AIInsightsService

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

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

    logging.info("Retrieving all regional hubs from BigQuery summary table...")
    try:
        # Fetches unique hubs from team_usa_data.regional_hubs_summary
        hubs = bq_service.get_all_hubs()
    except Exception as e:
        logging.error(f"Failed to fetch hubs from BigQuery: {e}")
        return

    if not hubs:
        logging.warning("No hubs found in regional_hubs_summary. Ensure geocoding and ingestion have been processed.")
        return

    logging.info(f"Processing {len(hubs)} hubs for AI insight generation...")

    for hub in hubs:
        hometown_id = hub.get('id')
        pretty_name = hub.get('pretty_city_name')

        logging.info(f"Checking narrative for: {pretty_name} ({hometown_id})")
        try:
            # get_narrative checks cache first; if missing, it generates via Gemini and saves to BigQuery
            await insights_service.get_narrative(hometown_id)
        except Exception as e:
            logging.error(f"Error processing narrative for {pretty_name}: {e}")

    logging.info("Batch hub narrative generation and caching complete.")

if __name__ == "__main__":
    asyncio.run(generate_hub_narratives())