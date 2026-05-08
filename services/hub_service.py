import logging
import pandas as pd
import requests
from google.cloud import bigquery
from typing import Dict, List, Optional
from .firestore_service import FirestoreService

class HubService:
    """
    Service to handle the creation and enrichment of Hometown Hubs.
    Manages regional mapping, geocoding integration, and BigQuery orchestration.
    """

    REGION_MAPPING = {
        'Pacific': ['CA', 'California', 'OR', 'Oregon', 'WA', 'Washington', 'HI', 'Hawaii', 'AK', 'Alaska'],
        'Mountain': ['CO', 'Colorado', 'UT', 'Utah', 'ID', 'Idaho', 'MT', 'Montana', 'WY', 'Wyoming'],
        'Midwest': ['MN', 'Minnesota', 'WI', 'Wisconsin', 'MI', 'Michigan', 'IL', 'Illinois', 'IN', 'Indiana', 'OH', 'Ohio'],
        'Northeast': ['NY', 'New York', 'PA', 'Pennsylvania', 'NJ', 'New Jersey', 'MA', 'Massachusetts', 'CT', 'Connecticut', 'RI', 'Rhode Island', 'VT', 'Vermont', 'NH', 'New Hampshire', 'ME', 'Maine', 'DC', 'District of Columbia', 'DE', 'Delaware'],
        'South': ['TX', 'Texas', 'FL', 'Florida', 'GA', 'Georgia', 'NC', 'North Carolina', 'SC', 'South Carolina', 'VA', 'Virginia', 'MD', 'Maryland', 'AL', 'Alabama', 'MS', 'Mississippi', 'LA', 'Louisiana', 'KY', 'Kentucky', 'TN', 'Tennessee', 'WV', 'West Virginia'],
        'The Heartland': ['IA', 'Iowa', 'MO', 'Missouri', 'KS', 'Kansas', 'NE', 'Nebraska', 'OK', 'Oklahoma', 'AR', 'Arkansas', 'SD', 'South Dakota', 'ND', 'North Dakota'],
        'The Desert Southwest': ['AZ', 'Arizona', 'NV', 'Nevada', 'NM', 'New Mexico']
    }

    def __init__(self, project_id: str, maps_api_key: str):
        self.project_id = project_id
        self.api_key = maps_api_key.strip("'").strip('"')
        self.client = bigquery.Client(project=project_id)
        self.firestore = FirestoreService(project_id=project_id)

    def determine_region(self, hometown: str) -> str:
        """Maps a hometown string to a US Region or 'Global'."""
        if not hometown or ',' not in hometown:
            return 'Global'
        
        state_part = hometown.split(',')[-1].strip().strip("'\".").strip()
        
        for region_name, states in self.REGION_MAPPING.items():
            if any(state_part.lower() == s.lower() for s in states):
                return region_name
                
        return 'Global'

    def get_geocode_data(self, hometown: str) -> dict:
        """Fetches Lat/Lng, Elevation, and generates IDs for a hometown."""
        if not hometown: return {}
        
        base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        try:
            resp = requests.get(base_url, params={"address": hometown.strip(), "key": self.api_key})
            resp.raise_for_status()
            data = resp.json()
            
            if data['status'] == 'OK' and data['results']:
                loc = data['results'][0]['geometry']['location']
                lat, lng = loc['lat'], loc['lng']
                
                elev_resp = requests.get("https://maps.googleapis.com/maps/api/elevation/json", 
                                         params={"locations": f"{lat},{lng}", "key": self.api_key})
                elev_resp.raise_for_status()
                elev_data = elev_resp.json()
                elevation = elev_data['results'][0]['elevation'] if elev_data['status'] == 'OK' else None
                
                hometown_id = hometown.lower().replace(' ', '-').replace(',', '').replace('.', '').replace("'", "").replace('"', '')
                region = self.determine_region(hometown)
                
                return {'lat': lat, 'lng': lng, 'elevation': elevation, 'hometown_id': hometown_id, 'region': region}
            else:
                logging.error(f"Geocoding failed for '{hometown}': {data.get('status')}")
        except Exception as e:
            logging.error(f"Unexpected geocoding error for {hometown}: {e}")
        return {}

    def _persist_registry_progress(self, df_registry: pd.DataFrame, dataset_id: str):
        """Saves current registry state to BigQuery."""
        table_ref = f"{self.project_id}.{dataset_id}.hometown_registry"
        schema = [
            bigquery.SchemaField("hometown", "STRING"),
            bigquery.SchemaField("total_athletes", "INTEGER"),
            bigquery.SchemaField("sports", "RECORD", mode="REPEATED", fields=[
                bigquery.SchemaField("sport", "STRING"),
                bigquery.SchemaField("count", "INTEGER"),
            ]),
            bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
            bigquery.SchemaField("lat", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("lng", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("regional_elevation", "FLOAT", mode="NULLABLE"),
            bigquery.SchemaField("hometown_id", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("region", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("narrative", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("narrative_timestamp", "TIMESTAMP", mode="NULLABLE"),
            bigquery.SchemaField("hub_image", "STRING", mode="NULLABLE"),
        ]
        job_config = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE")
        self.client.load_table_from_dataframe(df_registry, table_ref, job_config=job_config).result()
        logging.info("  --- Progress persisted to BigQuery ---")

    def process_hubs(self, dataset_id: str):
        """Orchestrates the geocoding and hub aggregation process."""
        # 1. Fetch Data
        logging.info("Fetching data for hub processing...")
        query = f"SELECT athlete_id, sport, hometown FROM `{self.project_id}.{dataset_id}.athletes`"
        df_raw = self.client.query(query).to_dataframe()
        
        if df_raw.empty:
            logging.info("No athlete data to process.")
            return

        # Initialize columns
        for col in ['lat', 'lng', 'regional_elevation', 'hometown_id', 'region', 'narrative', 'narrative_timestamp', 'hub_image']:
            df_raw[col] = None

        hometown_registry_table_ref = f"{self.project_id}.{dataset_id}.hometown_registry"
        try:
            df_registry = self.client.query(f"SELECT * FROM `{hometown_registry_table_ref}`").to_dataframe()
        except Exception:
            df_registry = pd.DataFrame(columns=['hometown', 'total_athletes', 'sports', 'load_timestamp', 'lat', 'lng', 'regional_elevation', 'hometown_id', 'region', 'narrative', 'narrative_timestamp', 'hub_image'])

        for col in ['lat', 'lng', 'regional_elevation', 'hometown_id', 'region', 'narrative', 'narrative_timestamp', 'hub_image']:
            if col not in df_registry.columns: df_registry[col] = None

        # 2. Geocoding Phase
        geo_cache = {}
        if not df_registry.empty:
            for _, row in df_registry.dropna(subset=['lat', 'lng']).iterrows():
                geo_cache[row['hometown']] = {
                    'lat': row['lat'], 'lng': row['lng'], 
                    'elevation': row['regional_elevation'], 
                    'hometown_id': row['hometown_id'], 
                    'region': row['region'],
                    'narrative': row.get('narrative'),
                    'narrative_timestamp': row.get('narrative_timestamp'),
                    'hub_image': row.get('hub_image')
                }

        unique_hometowns = sorted(list(set(df_raw['hometown'].dropna().unique()).union(set(df_registry['hometown'].dropna().unique()))))
        new_geocodes_since_save = 0
        
        for i, ht in enumerate(unique_hometowns, 1):
            if ht in geo_cache and geo_cache[ht].get('lat'): continue
            
            geo_cache[ht] = self.get_geocode_data(ht)
            if geo_cache[ht]: new_geocodes_since_save += 1
            
            if i % 25 == 0 or i == len(unique_hometowns):
                logging.info(f"  Geocoding progress: {i}/{len(unique_hometowns)}...")
                if new_geocodes_since_save >= 100:
                    self._persist_registry_progress(df_registry, dataset_id)
                    new_geocodes_since_save = 0

        if new_geocodes_since_save > 0:
            self._persist_registry_progress(df_registry, dataset_id)

        # 3. Enrichment
        def enrich(row):
            geo = geo_cache.get(row['hometown'], {})
            ht_str = str(row['hometown']) if row['hometown'] else ""
            return pd.Series([
                geo.get('lat'), geo.get('lng'), geo.get('elevation'),
                geo.get('hometown_id', ht_str.lower().replace(' ', '-').replace(',', '').replace('.', '').replace("'", "").replace('"', '')),
                geo.get('region', self.determine_region(ht_str)),
                geo.get('narrative'),
                geo.get('narrative_timestamp'),
                geo.get('hub_image')
            ])

        logging.info("Enriching DataFrames...")
        df_raw[['lat', 'lng', 'regional_elevation', 'hometown_id', 'region', 'narrative', 'narrative_timestamp', 'hub_image']] = df_raw.apply(enrich, axis=1, result_type='expand')
        
        # 4. Hub Aggregation
        df_hubs = df_raw.dropna(subset=['lat', 'lng']).groupby(
            ['hometown_id', 'region', 'sport', 'lat', 'lng', 'regional_elevation']
        ).agg(
            athlete_count=('athlete_id', 'count'),
            athlete_ids=('athlete_id', lambda x: ', '.join(x.astype(str)))
        ).reset_index().rename(columns={'sport': 'sport_name'})
        df_hubs['load_timestamp'] = pd.Timestamp.now(tz='UTC')

        # 5. Summary Aggregation
        df_summary = df_raw.dropna(subset=['lat', 'lng']).groupby(
            ['hometown_id', 'hometown', 'region', 'lat', 'lng', 'regional_elevation']
        ).agg(
            total_athlete_count=('athlete_id', 'count'),
            sports=('sport', lambda x: [{"sport": s, "count": int(c)} for s, c in sorted(x.value_counts().items(), key=lambda item: item[1], reverse=True)]),
            narrative=('narrative', 'first'),
            narrative_timestamp=('narrative_timestamp', 'first'),
            hub_image=('hub_image', 'first')
        ).reset_index()
        df_summary['load_timestamp'] = pd.Timestamp.now(tz='UTC')

        # 6. Final Loads
        logging.info("Performing final BigQuery loads...")
        self.client.load_table_from_dataframe(
            df_hubs, 
            f"{self.project_id}.{dataset_id}.hometown_hubs",
            job_config=bigquery.LoadJobConfig(
                # Clustering by hometown_id significantly speeds up point lookups
                clustering_fields=["hometown_id"],
                schema=[
                    bigquery.SchemaField("hometown_id", "STRING"),
                    bigquery.SchemaField("region", "STRING"),
                    bigquery.SchemaField("sport_name", "STRING"),
                    bigquery.SchemaField("lat", "FLOAT"),
                    bigquery.SchemaField("lng", "FLOAT"),
                    bigquery.SchemaField("regional_elevation", "FLOAT"),
                    bigquery.SchemaField("athlete_count", "INTEGER"),
                    bigquery.SchemaField("athlete_ids", "STRING"),
                    bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
                ],
                write_disposition="WRITE_TRUNCATE"
            )
        ).result()

        # 7. Sync to Firestore Serving Layer
        logging.info("Synchronizing summary data to Firestore serving layer...")
        # Prepare the summary data for the map (rename columns to match frontend expectations if needed)
        df_serving = df_summary.copy()
        df_serving = df_serving.rename(columns={'hometown': 'pretty_city_name', 'total_athlete_count': 'athlete_count'})
        self.firestore.sync_from_dataframe(df_serving)
        logging.info("Firestore synchronization complete.")

        self.client.load_table_from_dataframe(
            df_summary, 
            f"{self.project_id}.{dataset_id}.regional_hubs_summary",
            job_config=bigquery.LoadJobConfig(
                # Clustering by hometown_id and region optimizes the map view and drawer
                clustering_fields=["hometown_id", "region"],
                schema=[
                    bigquery.SchemaField("hometown_id", "STRING"),
                    bigquery.SchemaField("hometown", "STRING"),
                    bigquery.SchemaField("region", "STRING"),
                    bigquery.SchemaField("lat", "FLOAT"),
                    bigquery.SchemaField("lng", "FLOAT"),
                    bigquery.SchemaField("regional_elevation", "FLOAT"),
                    bigquery.SchemaField("total_athlete_count", "INTEGER"),
                    bigquery.SchemaField("sports", "RECORD", mode="REPEATED", fields=[
                        bigquery.SchemaField("sport", "STRING"),
                        bigquery.SchemaField("count", "INTEGER"),
                    ]),
                    bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
                    bigquery.SchemaField("narrative", "STRING", mode="NULLABLE"),
                    bigquery.SchemaField("narrative_timestamp", "TIMESTAMP", mode="NULLABLE"),
                    bigquery.SchemaField("hub_image", "STRING", mode="NULLABLE"),
                ],
                write_disposition="WRITE_TRUNCATE"
            )
        ).result()