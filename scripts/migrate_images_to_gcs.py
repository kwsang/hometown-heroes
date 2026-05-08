import os
import base64
import logging
import io
from google.cloud import bigquery
from google.cloud import storage # Import storage here
from PIL import Image
from dotenv import load_dotenv
import concurrent.futures
import threading

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def _process_single_image(row, project_id: str, bucket_name: str, storage_client: storage.Client):
    """Processes a single image migration task."""
    hid = row.hometown_id
    img_data = row.hub_image

    # Skip if already migrated to the new optimized format
    if img_data.startswith("http") and img_data.endswith(".webp"):
        logging.debug(f"Skipping {hid}: already migrated.")
        return

    try:
        logging.info(f"Migrating image for {hid}...")

        # Sanitize input: Remove potential data URI prefix and whitespace
        if "," in img_data:
            img_data = img_data.split(",")[-1]
        img_data = img_data.strip()

        # Guard: Valid Base64 images are typically > 1KB (approx 1333 characters)
        if len(img_data) < 200:
            logging.warning(f"Skipping {hid}: Image data is too short or contains placeholder text.")
            return None

        image_bytes = base64.b64decode(img_data)
        
        # Process image to reduce size and optimize
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Resize to 400px (ideal for side drawer thumbnails)
            target_width = 400
            if img.width > target_width:
                w_percent = (target_width / float(img.width))
                h_size = int((float(img.height) * float(w_percent)))
                img = img.resize((target_width, h_size), Image.Resampling.LANCZOS)
            
            # Convert to WebP with lossy compression for maximum size reduction
            output = io.BytesIO()
            img.save(output, format="WEBP", quality=80, method=6)
            processed_bytes = output.getvalue()

        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(f"hubs/{hid}.webp")
        blob.upload_from_string(processed_bytes, content_type="image/webp")
        
        logging.info(f"Successfully uploaded {hid} to GCS.")
        return {"hid": hid, "url": f"https://storage.googleapis.com/{bucket_name}/hubs/{hid}.webp"}
    except Exception as e:
        logging.error(f"Failed to migrate {hid}: {e}")
        return None

def migrate_images():
    """
    Reads Base64 images from BigQuery, uploads them to GCS, 
    and updates the BigQuery record with the public URL.
    """
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    bucket_name = os.getenv("GCS_BUCKET_NAME", f"{project_id}-hub-images")

    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT not set.")
        return

    bq_client = bigquery.Client(project=project_id)
    storage_client = storage.Client(project=project_id)
    
    # Ensure bucket exists and is public (if desired)
    bucket = storage_client.bucket(bucket_name)
    if not bucket.exists():
        logging.info(f"Creating bucket: {bucket_name}")
        bucket.create(location="us-central1")
        try:
            # Make public if not already, for direct access
            policy = bucket.get_iam_policy(requested_policy_version=3)
            if not any(binding.role == 'roles/storage.objectViewer' and 'allUsers' in binding.members for binding in policy.bindings):
                policy.bindings.add(storage.Policy.Binding('roles/storage.objectViewer', ['allUsers']))
                bucket.set_iam_policy(policy)
                logging.info(f"Made bucket '{bucket_name}' publicly readable.")
        except Exception as e:
            logging.warning(f"Could not make bucket '{bucket_name}' publicly readable: {e}. Ensure permissions are set if direct public access is desired.")

    query = f"SELECT hometown_id, hub_image FROM `{project_id}.team_usa_data.regional_hubs_summary` WHERE hub_image IS NOT NULL"
    rows = bq_client.query(query).result()

    # Use ThreadPoolExecutor for parallel processing
    # Adjust max_workers based on your system's CPU cores and network bandwidth
    # A common heuristic is 2x CPU cores for I/O-bound tasks.
    max_workers = int(os.getenv("MIGRATION_WORKERS", 8)) 
    logging.info(f"Starting image migration with {max_workers} workers...")
    
    migration_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_process_single_image, row, project_id, bucket_name, storage_client) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            if result:
                migration_results.append(result)

    if migration_results:
        logging.info(f"All images processed. Performing batch update for {len(migration_results)} records in BigQuery...")
        
        # Use a MERGE statement with UNNEST to update all rows in a single job
        merge_query = f"""
            MERGE `{project_id}.team_usa_data.regional_hubs_summary` T
            USING UNNEST(@updates) S
            ON T.hometown_id = S.hid
            WHEN MATCHED THEN
              UPDATE SET hub_image = S.url
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("updates", "RECORD", migration_results)
            ]
        )
        bq_client.query(merge_query, job_config=job_config).result()
        logging.info("BigQuery batch update complete.")
    else:
        logging.info("No records required updating.")

if __name__ == "__main__":
    migrate_images()