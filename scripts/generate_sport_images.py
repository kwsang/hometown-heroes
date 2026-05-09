import os
import logging
import io
import sys
import time
from google.api_core import exceptions
from google.cloud import bigquery
from google.cloud import storage
from vertexai.preview.vision_models import ImageGenerationModel
from PIL import Image
from dotenv import load_dotenv

# Add project root for service resolution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def _process_sport_image(sport_name, project_id, bucket_name, model):
    """Generates, optimizes, and uploads a sport clipart image."""
    sport_id = sport_name.lower().replace(" ", "_").replace("/", "_")
    gcs_path = f"sports/{sport_id}.webp"
    storage_client = storage.Client(project=project_id)
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    logging.info(f"Generating image for sport: {sport_name}")
    
    prompt = (
        f"A vibrant and modern flat vector clipart illustration representing the sport of {sport_name}. "
        "Clean minimal design, bold colors, professional aesthetic, isolated on transparent background. "
        "If the sport is a PARALYMPIC sport, incorporate subtle design elements that evoke inclusivity and adaptive sports. Do NOT make it untasteful or stereotypical. Focus on the essence of the sport while ensuring the image is respectful and empowering. "
        "No text, no photorealistic details."
    )

    max_retries = 3
    retry_wait = 10  # Initial wait time in seconds if 429 is encountered

    for attempt in range(max_retries):
        try:
            # Generate using Imagen 3.0
            response = model.generate_images(
                prompt=prompt,
                number_of_images=1,
                language="en",
                aspect_ratio="1:1"
            )

            if response.images:
                image_bytes = response.images[0]._image_bytes
                
                # Optimize for web: 400x400 WebP
                with Image.open(io.BytesIO(image_bytes)) as img:
                    img = img.resize((400, 400), Image.Resampling.LANCZOS)
                    output = io.BytesIO()
                    img.save(output, format="WEBP", quality=85)
                    optimized_bytes = output.getvalue()

                blob.upload_from_string(optimized_bytes, content_type="image/webp")
                url = f"https://storage.googleapis.com/{bucket_name}/{gcs_path}"
                logging.info(f"Successfully uploaded {sport_name} icon to GCS.")
                return {"sport": sport_name, "url": url}

        except exceptions.ResourceExhausted:
            if attempt < max_retries - 1:
                logging.warning(f"Quota exceeded (429) for {sport_name}. Retrying in {retry_wait}s...")
                time.sleep(retry_wait)
                retry_wait += 10  # Increase wait by 10 seconds for the next retry
            else:
                logging.error(f"Max retries reached for {sport_name} due to quota exhaustion.")
        except Exception as e:
            logging.error(f"Failed to generate image for {sport_name}: {e}")
            break  # Exit loop for non-retryable exceptions

    return None

def generate_sport_images():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    bucket_name = os.getenv("GCS_BUCKET_NAME", f"{project_id}-hub-images")
    dataset_id = "team_usa_data"
    table_id = "sport_summary"

    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT is not set.")
        return

    bq_client = bigquery.Client(project=project_id)

    # 0. Check if the sport_image column exists in the table schema
    try:
        table = bq_client.get_table(f"{project_id}.{dataset_id}.{table_id}")
        if not any(field.name == "sport_image" for field in table.schema):
            logging.error(f"Table '{table_id}' is missing the 'sport_image' column. Run 'services/create_sport_summary_table.py' first.")
            return
    except Exception as e:
        logging.error(f"Could not access table '{table_id}': {e}")
        return

    model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")

    # 1. Identify sports missing images
    query = f"""
        SELECT sport_name 
        FROM `{project_id}.{dataset_id}.{table_id}` 
        WHERE sport_image IS NULL
    """
    try:
        sports = [row.sport_name for row in bq_client.query(query).result()]
    except Exception as e:
        logging.error(f"Could not fetch sports from BQ: {e}")
        return

    if not sports:
        logging.info("All sports already have cached images.")
        return

    logging.info(f"Processing {len(sports)} sport images...")

    # 2. Throttled Generation and Upload
    # Quota: 10 requests per minute -> 1 request every 6 seconds.
    results = []
    request_delay = 6.0 # seconds

    for i, sport in enumerate(sports):
        res = _process_sport_image(sport, project_id, bucket_name, model)
        if res:
            results.append(res)
        
        # Delay after each request (except the last one) to respect the 10 RPM quota
        if i < len(sports) - 1:
            time.sleep(request_delay)

    # 3. Batch Update BigQuery
    if results:
        logging.info(f"Updating BigQuery with {len(results)} image references...")
        merge_query = f"""
            MERGE `{project_id}.{dataset_id}.{table_id}` T
            USING UNNEST(@updates) S
            ON T.sport_name = S.sport
            WHEN MATCHED THEN
              UPDATE SET sport_image = S.url
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter(
                    "updates", 
                    "RECORD", 
                    [
                        bigquery.StructQueryParameter(
                            "row",
                            bigquery.ScalarQueryParameter("sport", "STRING", r["sport"]),
                            bigquery.ScalarQueryParameter("url", "STRING", r["url"])
                        ) for r in results
                    ]
                )
            ]
        )
        bq_client.query(merge_query, job_config=job_config).result()
        logging.info("Sport summary table updated successfully.")
    else:
        logging.warning("No images were successfully generated.")

if __name__ == "__main__":
    generate_sport_images()