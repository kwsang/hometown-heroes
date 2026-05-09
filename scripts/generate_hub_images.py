import os
import asyncio
import logging
import sys
import vertexai
from google.api_core import exceptions as google_exceptions
from google.cloud import bigquery
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.bigquery_service import BigQueryService
from services.image_generation_service import ImageGenerationService
from services.firestore_service import FirestoreService

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def _generate_image_with_retry(hub, image_service):
    """Generates a hub image with sequential retry logic due to low Imagen RPM."""
    hometown_id = hub.get('id')
    pretty_name = hub.get('pretty_city_name')
    region = hub.get('region', 'USA')
    
    max_retries = 3
    retry_wait = 15 # Longer wait for Imagen
    
    for attempt in range(max_retries):
        try:
            logging.info(f"Processing: {pretty_name} ({hometown_id}) [Attempt {attempt+1}]")
            # image_service.get_hub_image handles GCS upload and individual updates
            url = await image_service.get_hub_image(hometown_id, pretty_name, region)
            if url:
                return {"hid": hometown_id, "url": url}
            break 
            
        except google_exceptions.ResourceExhausted:
            if attempt < max_retries - 1:
                logging.warning(f"Quota exceeded for {pretty_name}. Retrying in {retry_wait}s...")
                await asyncio.sleep(retry_wait)
                retry_wait += 15
            else:
                logging.error(f"Max retries reached for {pretty_name}.")
        except Exception as e:
            logging.error(f"Error processing {pretty_name}: {e}")
            break
    return None

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
    firestore_service = FirestoreService(project_id=project_id)

    logging.info("Retrieving all regional hubs from BigQuery summary table...")
    try:
        hubs = bq_service.get_all_hubs()
    except Exception as e:
        logging.error(f"Failed to fetch hubs from BigQuery: {e}")
        return

    # 1. Filter for hubs missing images
    hubs_to_process = [h for h in hubs if not bq_service.get_cached_image(h['id'])]

    if not hubs_to_process:
        logging.info("All hubs already have images.")
        return

    logging.info(f"Processing {len(hubs_to_process)} hubs for image generation...")

    # 2. Sequential throttled processing
    results = []
    request_delay = 10.0 # ~6 RPM 
    
    for i, hub in enumerate(hubs_to_process):
        res = await _generate_image_with_retry(hub, image_service)
        if res:
            results.append(res)
        
        if i < len(hubs_to_process) - 1:
            await asyncio.sleep(request_delay)

    logging.info(f"Batch hub image generation complete. {len(results)} assets created.")

if __name__ == "__main__":
    asyncio.run(generate_hub_images())