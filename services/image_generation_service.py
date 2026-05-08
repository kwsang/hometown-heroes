import logging
import os
import io
import asyncio
from typing import Optional
from vertexai.preview.vision_models import ImageGenerationModel
from google.cloud import bigquery
from google.cloud import storage
from PIL import Image
from .bigquery_service import BigQueryService
from .firestore_service import FirestoreService

class ImageGenerationService:
    """
    Service to handle AI image generation for hubs using Imagen.
    Implements write-through caching in BigQuery.
    """
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.bigquery = BigQueryService(project_id=project_id)
        self.firestore = FirestoreService(project_id=project_id)
        self.storage_client = storage.Client(project=project_id)
        # Default bucket name based on project ID
        self.bucket_name = os.getenv("GCS_BUCKET_NAME", f"{project_id}-hub-images")
        
        # Initialize the Imagen model
        self.model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")

    async def get_hub_image(self, hometown_id: str, pretty_name: str, region: str) -> Optional[str]:
        """
        Returns the GCS URL or base64 encoded image for the hub. 
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
            # Run the synchronous Imagen call in a separate thread to avoid blocking the event loop
            response = await asyncio.to_thread(
                self.model.generate_images,
                prompt=prompt,
                number_of_images=1,
                language="en",
                aspect_ratio="4:3"
            )

            if response.images:
                image_bytes = response.images[0]._image_bytes
                
                # 3. Upload to GCS
                gcs_url = self._upload_to_gcs(hometown_id, image_bytes)

                # 4. Persist URL to cache (BigQuery) and Serving Layer (Firestore)
                logging.info(f"Caching generated image for {pretty_name} ({hometown_id}).")
                self._cache_image_url(hometown_id, gcs_url)
                self.firestore.update_field(hometown_id, "hub_image", gcs_url)
                return gcs_url

        except Exception as e:
            logging.error(f"Image generation failed for {pretty_name}: {e}")
        
        return None

    def _upload_to_gcs(self, hometown_id: str, image_bytes: bytes) -> str:
        """Uploads image to GCS and returns the public URL."""
        bucket = self.storage_client.bucket(self.bucket_name)
        blob = bucket.blob(f"hubs/{hometown_id}.webp")

        # Optimize and resize image before upload
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Resize to 400px width (ideal for the side drawer)
            target_width = 400
            if img.width > target_width:
                w_percent = (target_width / float(img.width))
                h_size = int((float(img.height) * float(w_percent)))
                img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
            
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=80, method=6)
            processed_bytes = output.getvalue()
        
        blob.upload_from_string(processed_bytes, content_type="image/webp")
        return f"https://storage.googleapis.com/{self.bucket_name}/hubs/{hometown_id}.webp"

    def _cache_image_url(self, hometown_id: str, image_url: str):
        """Internal helper to save the GCS URL to BigQuery."""
        query = f"""
            UPDATE `{self.project_id}.team_usa_data.regional_hubs_summary`
            SET hub_image = @image_url
            WHERE hometown_id = @hometown_id
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("image_url", "STRING", image_url),
                bigquery.ScalarQueryParameter("hometown_id", "STRING", hometown_id)
            ]
        )
        self.bigquery.client.query(query, job_config=job_config).result()
        logging.info(f"Image URL for {hometown_id} cached in BigQuery.")