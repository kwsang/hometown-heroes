import os
import asyncio
import logging
import sys
import vertexai
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bigquery_service import BigQueryService
from services.image_generation_service import ImageGenerationService

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def generate_hub_images():
    """
    Iterates through all regional hubs in BigQuery and triggers the 
    AI image generation and caching process using Imagen.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    
    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    # Initialize Vertex AI for the image generation model
    vertexai.init(project=project_id, location=location)

    # Initialize services
    bq_service = BigQueryService(project_id=project_id)
    image_service = ImageGenerationService(project_id=project_id)

    logging.info("Retrieving all regional hubs from BigQuery summary table...")
    try:
        # Fetches unique hubs from team_usa_data.regional_hubs_summary
        hubs = bq_service.get_all_hubs()
    except Exception as e:
        logging.error(f"Failed to fetch hubs from BigQuery: {e}")
        return

    if not hubs:
        logging.warning("No hubs found in regional_hubs_summary. Ensure geocoding has been processed.")
        return

    logging.info(f"Processing {len(hubs)} hubs for image generation...")

    for hub in hubs:
        hometown_id = hub.get('id')
        pretty_name = hub.get('pretty_city_name')
        region = hub.get('region', 'USA')

        logging.info(f"Checking image for: {pretty_name} ({hometown_id})")
        try:
            # get_hub_image checks cache first; if missing, it generates and saves to BigQuery
            await image_service.get_hub_image(hometown_id, pretty_name, region)
        except Exception as e:
            logging.error(f"Error processing image for {pretty_name}: {e}")

    logging.info("Batch hub image generation and caching complete.")

if __name__ == "__main__":
    asyncio.run(generate_hub_images())