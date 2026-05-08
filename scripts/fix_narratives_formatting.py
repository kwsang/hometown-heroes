import os
import re
import logging
import sys
from google.cloud import bigquery
from dotenv import load_dotenv

# Add project root to path for services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.firestore_service import FirestoreService

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def fix_narratives():
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    dataset_id = "team_usa_data"
    
    if not project_id:
        logging.error("GOOGLE_CLOUD_PROJECT environment variable is not set.")
        return

    bq_client = bigquery.Client(project=project_id)
    firestore_service = FirestoreService(project_id=project_id)
    
    # 1. Fetch narratives from BigQuery
    query = f"SELECT hometown_id, narrative FROM `{project_id}.{dataset_id}.regional_hubs_summary` WHERE narrative IS NOT NULL"
    try:
        df = bq_client.query(query).to_dataframe()
    except Exception as e:
        logging.error(f"Failed to fetch narratives from BigQuery: {e}")
        return
    
    # Official Hub Regions to be wrapped in <strong> tags
    regions = [
        'Pacific', 'Mountain', 'Midwest', 'Northeast', 'South', 
        'The Heartland', 'The Desert Southwest', 'Global'
    ]
    
    updates = []
    for _, row in df.iterrows():
        hid = row['hometown_id']
        old_narrative = row['narrative']
        new_narrative = old_narrative
        
        # A. Fix [City] [Year] placeholders to compliant terminology
        # Replaces template placeholders with official Games terminology
        new_narrative = new_narrative.replace("Olympic Games [City] [Year]", "LA28 Olympic and Paralympic Games")
        new_narrative = new_narrative.replace("Paralympic Games [City] [Year]", "LA28 Olympic and Paralympic Games")
        new_narrative = new_narrative.replace("Olympic Winter Games [City] [Year]", "Olympic Winter Games Milano Cortina 2026")
        new_narrative = new_narrative.replace("Paralympic Winter Games [City] [Year]", "Paralympic Winter Games Milano Cortina 2026")
        new_narrative = new_narrative.replace("[City] [Year]", "LA28")
        
        # B. Convert Markdown bold (**) to HTML <strong> tags
        new_narrative = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', new_narrative)
        
        # C. Ensure Region names are bolded (if they appear as plain text)
        for region in regions:
            # Matches region name if it's a whole word and not already inside strong tags
            pattern = rf'(?<!<strong>)\b{re.escape(region)}\b(?!</strong>)'
            new_narrative = re.sub(pattern, f"<strong>{region}</strong>", new_narrative)

        if new_narrative != old_narrative:
            updates.append({"hid": hid, "narrative": new_narrative})

    if not updates:
        logging.info("No narratives required formatting fixes.")
        return

    logging.info(f"Found {len(updates)} narratives to fix. Updating BigQuery...")
    
    # 2. Batch update BigQuery using a MERGE statement with UNNEST
    merge_query = f"""
        MERGE `{project_id}.{dataset_id}.regional_hubs_summary` T
        USING UNNEST(@updates) S
        ON T.hometown_id = S.hid
        WHEN MATCHED THEN
          UPDATE SET narrative = S.narrative, narrative_timestamp = CURRENT_TIMESTAMP()
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter(
                "updates", 
                "RECORD", 
                [
                    bigquery.StructQueryParameter(
                        "row",
                        bigquery.ScalarQueryParameter("hid", "STRING", u["hid"]),
                        bigquery.ScalarQueryParameter("narrative", "STRING", u["narrative"])
                    ) for u in updates
                ]
            )
        ]
    )
    
    bq_client.query(merge_query, job_config=job_config).result()
    
    # 3. Synchronize directly to Firestore to update the UI immediately
    logging.info(f"Syncing {len(updates)} updated narratives to Firestore...")
    for u in updates:
        firestore_service.update_field(u['hid'], "narrative", u['narrative'])
        
    logging.info("Narrative formatting and synchronization complete.")

if __name__ == "__main__":
    fix_narratives()