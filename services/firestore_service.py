import logging
import math
import time
from typing import List, Dict, Any, Optional
from google.cloud import firestore

class FirestoreService:
    """
    High-performance serving layer for Hometown Heroes.
    Handles low-latency document retrieval for the frontend.
    """
    def __init__(self, project_id: str):
        self.db = firestore.Client(project=project_id)
        self.collection_name = "hubs"

    def get_all_hubs(self) -> List[Dict[str, Any]]:
        """Fetches all hub summaries for map rendering."""
        start_time = time.time()
        docs = self.db.collection(self.collection_name).stream()
        hubs = []
        for doc in docs:
            hub_data = doc.to_dict()
            hub_data['id'] = doc.id
            hubs.append(hub_data)
        
        duration = time.time() - start_time
        logging.info(f"Firestore: Fetched {len(hubs)} hubs in {duration:.4f}s")
        return hubs

    def get_hub(self, hometown_id: str) -> Optional[Dict[str, Any]]:
        """Fetches a specific hub's statistics and metadata."""
        doc_ref = self.db.collection(self.collection_name).document(hometown_id)
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None

    def upsert_hub(self, hometown_id: str, data: Dict[str, Any]):
        """Updates or creates a hub document (used by ETL sync)."""
        doc_ref = self.db.collection(self.collection_name).document(hometown_id)
        doc_ref.set(data, merge=True)

    def update_field(self, hometown_id: str, field: str, value: Any):
        """Updates a specific field (e.g., narrative or image_url)."""
        doc_ref = self.db.collection(self.collection_name).document(hometown_id)
        doc_ref.update({field: value})

    def sync_from_dataframe(self, df):
        """Batch synchronizes a pandas DataFrame to Firestore."""
        batch = self.db.batch()
        count = 0
        for _, row in df.iterrows():
            doc_id = row['hometown_id']
            if not doc_id:
                continue
                
            doc_ref = self.db.collection(self.collection_name).document(doc_id)
            
            # Clean and convert data to native Python types for Firestore compatibility
            clean_data = {}
            for k, v in row.to_dict().items():
                # Skip nulls and NaNs
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    continue
                # Convert numpy types to native Python types
                clean_data[k] = getattr(v, 'tolist', lambda: v)() if hasattr(v, 'dtype') else v

            batch.set(doc_ref, clean_data, merge=True)
            count += 1
            if count >= 400: # Firestore batch limit is 500
                batch.commit()
                batch = self.db.batch()
                count = 0
        batch.commit()