import logging
import base64
from typing import Optional
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import bigquery
from services.bigquery_service import BigQueryService

class ImageGenerationService:
    """
    Service to handle AI image generation for hubs using Imagen.
    Implements write-through caching in BigQuery.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.bigquery = BigQueryService(project_id=project_id)
        # Initialize the Imagen model
        self.model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001") # Consider pinning a specific version

    async def get_hub_image(self, hometown_id: str, pretty_name: str, region: str) -> Optional[str]:
        """
        Returns a base64 encoded image for the hub. 
        Checks BigQuery cache first.
        """
        # 1. Check BigQuery Cache
        try:
            cached_image = self.bigquery.get_cached_image(hometown_id)
            if cached_image:
                logging.info(f"Image for {pretty_name} ({hometown_id}) found in cache.")
                return cached_image
        except Exception as e:
            logging.error(f"Error fetching cached image for {hometown_id}: {e}")
            # Log the full traceback for better debugging
            # Continue to generate if cache check fails

        # 2. Generate Image if not cached
        logging.info(f"Generating new image for hub: {pretty_name}")
        prompt = (
            f"A vibrant and modern flat vector clipart illustration of the natural landscape in {pretty_name}, {region}. "
            "The scene should feature nationally recognizable natural landmarks, or falling back to iconic local structures if available. "
            "Clean minimal design, bold colors, inspiring atmosphere. No people, no text."
        )

        try:
            # Generate the image
            response = self.model.generate_images(
                prompt=prompt,
                number_of_images=1,
                language="en",
                aspect_ratio="4:3"
            )

            if response.images:
                image_bytes = response.images[0]._image_bytes
                base64_image = base64.b64encode(image_bytes).decode('utf-8')

                # 3. Persist to cache (Write-through)
                logging.info(f"Caching generated image for {pretty_name} ({hometown_id}).")
                self._cache_image(hometown_id, base64_image)
                return base64_image

        except Exception as e:
            logging.error(f"Image generation failed for {pretty_name}: {e}")
            # Log the full traceback for better debugging
        
        return None

    def _cache_image(self, hometown_id: str, base64_data: str):
        """Internal helper to save the image to BigQuery."""
        query = f"""
            UPDATE `{self.project_id}.team_usa_data.regional_hubs_summary`
            SET hub_image = @image_data
            WHERE hometown_id = @hometown_id
        """
        job_config = bigquery.QueryJobConfig( # Reference bigquery.QueryJobConfig directly
            query_parameters=[
                bigquery.ScalarQueryParameter("image_data", "STRING", base64_data), # Reference bigquery.ScalarQueryParameter directly
                bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id) # Reference bigquery.ScalarQueryParameter directly
            ]
        )
        self.bigquery.client.query(query, job_config=job_config).result()
        logging.info(f"Image for {hometown_id} successfully cached in BigQuery.")