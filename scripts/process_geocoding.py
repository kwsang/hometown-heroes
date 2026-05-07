import os
import logging
import pandas as pd
from google.cloud import bigquery
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

REGION_MAPPING = {
    'Pacific': ['CA', 'California', 'OR', 'Oregon', 'WA', 'Washington', 'HI', 'Hawaii', 'AK', 'Alaska'],
    'Mountain': ['CO', 'Colorado', 'UT', 'Utah', 'ID', 'Idaho', 'MT', 'Montana', 'WY', 'Wyoming'],
    'Midwest': ['MN', 'Minnesota', 'WI', 'Wisconsin', 'MI', 'Michigan', 'IL', 'Illinois', 'IN', 'Indiana', 'OH', 'Ohio'],
    'Northeast': ['NY', 'New York', 'PA', 'Pennsylvania', 'NJ', 'New Jersey', 'MA', 'Massachusetts', 'CT', 'Connecticut', 'RI', 'Rhode Island', 'VT', 'Vermont', 'NH', 'New Hampshire', 'ME', 'Maine', 'DC', 'District of Columbia', 'DE', 'Delaware'],
    'South': ['TX', 'Texas', 'FL', 'Florida', 'GA', 'Georgia', 'NC', 'North Carolina', 'SC', 'South Carolina', 'VA', 'Virginia', 'MD', 'Maryland', 'AL', 'Alabama', 'MS', 'Mississippi', 'LA', 'Louisiana', 'KY', 'Kentucky', 'TN', 'Tennessee', 'WV', 'West Virginia'],
    'The Heartland': ['IA', 'Iowa', 'MO', 'Missouri', 'KS', 'Kansas', 'NE', 'Nebraska', 'OK', 'Oklahoma', 'AR', 'Arkansas', 'SD', 'South Dakota', 'ND', 'North Dakota'],
    'The Desert Southwest': ['AZ', 'Arizona', 'NV', 'Nevada', 'NM', 'New Mexico']
}

def determine_region(hometown: str) -> str:
    if not hometown or ',' not in hometown:
        return 'Global'
    # Split by comma and take the last part (the state/country candidate)
    state_part = hometown.split(',')[-1].strip()
    
    # Strip quotes and trailing punctuation that cause lookup failures
    state_part = state_part.strip("'\".").strip()
    
    for region_name, states in REGION_MAPPING.items():
        # Perform case-insensitive check against the region mapping
        if any(state_part.lower() == s.lower() for s in states):
            return region_name
            
    return 'Global'

def get_geocode_data(hometown: str, api_key: str) -> dict:
    if not hometown: return {}
    api_key = api_key.strip("'").strip('"')
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(base_url, params={"address": hometown.strip(), "key": api_key})
        resp.raise_for_status()
        data = resp.json()
        if data['status'] == 'OK' and data['results']:
            loc = data['results'][0]['geometry']['location']
            lat, lng = loc['lat'], loc['lng']
            
            elev_resp = requests.get("https://maps.googleapis.com/maps/api/elevation/json", 
                                     params={"locations": f"{lat},{lng}", "key": api_key})
            elev_resp.raise_for_status()
            elev_data = elev_resp.json()
            elevation = elev_data['results'][0]['elevation'] if elev_data['status'] == 'OK' else None
            
            # Clean the ID generation by removing quotes as well as spaces and dots
            hometown_id = hometown.lower().replace(' ', '-').replace(',', '').replace('.', '').replace("'", "").replace('"', '')
            region = determine_region(hometown)
            return {'lat': lat, 'lng': lng, 'elevation': elevation, 'hometown_id': hometown_id, 'region': region}
        else:
            error_msg = data.get('error_message', 'No additional details provided.')
            logging.error(f"Geocoding failed for '{hometown}': {data.get('status')} - {error_msg}")
    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed for '{hometown}': {e}")
    except Exception as e:
        logging.error(f"Unexpected geocoding error for {hometown}: {e}")
    return {}

def process_geocoding_service(project_id: str, dataset_id: str):
    client = bigquery.Client(project=project_id)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key: raise ValueError("GOOGLE_MAPS_API_KEY not set.")

    # 1. Fetch raw data and current registry to save progress and avoid redundant API calls
    logging.info("Fetching raw athlete data and existing registry...")
    query = f"SELECT athlete_id, sport, hometown FROM `{project_id}.{dataset_id}.athletes`"
    df_raw = client.query(query).to_dataframe()
    
    if df_raw.empty:
        logging.info("No raw athlete data found to process.")
        return

    hometown_registry_table_ref = f"{project_id}.{dataset_id}.hometown_registry"
    try:
        df_registry = client.query(f"SELECT * FROM `{hometown_registry_table_ref}`").to_dataframe()
        logging.info(f"Loaded {len(df_registry)} records from hometown_registry.")
    except Exception as e:
        logging.warning(f"hometown_registry table not found. Starting with empty registry. Error: {e}")
        df_registry = pd.DataFrame(columns=['hometown', 'total_athletes', 'sports', 'load_timestamp', 'lat', 'lng', 'regional_elevation', 'hometown_id', 'region'])

    geo_cache = {}
    # Pre-populate cache from existing geocoding data in registry to enable "resume" capability
    if not df_registry.empty:
        for _, row in df_registry.dropna(subset=['lat', 'lng']).iterrows():
            geo_cache[row['hometown']] = {
                'lat': row['lat'], 'lng': row['lng'], 
                'elevation': row['regional_elevation'], 
                'hometown_id': row['hometown_id'], 
                'region': row['region']
            }
    logging.info(f"Initialized cache with {len(geo_cache)} existing geocodes.")

    def persist_registry_progress():
        """Internal helper to save current geocoding results to BigQuery."""
        logging.info("  --- Saving geocoding progress to BigQuery registry ---")
        # Update df_registry from cache
        for index, row in df_registry.iterrows():
            ht = row['hometown']
            if ht in geo_cache and geo_cache[ht] and 'lat' in geo_cache[ht]:
                geo = geo_cache[ht]
                df_registry.at[index, 'lat'] = geo.get('lat')
                df_registry.at[index, 'lng'] = geo.get('lng')
                df_registry.at[index, 'regional_elevation'] = geo.get('elevation')
                df_registry.at[index, 'hometown_id'] = geo.get('hometown_id')
                df_registry.at[index, 'region'] = geo.get('region')
        
        registry_schema = [
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
        ]
        job_config = bigquery.LoadJobConfig(schema=registry_schema, write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df_registry, hometown_registry_table_ref, job_config=job_config).result()

    # 2. Comprehensive Geocoding Phase
    # Get all unique hometowns that need geocoding from both athletes and registry
    unique_hometowns = sorted(list(set(df_raw['hometown'].dropna().unique()).union(set(df_registry['hometown'].dropna().unique()))))
    logging.info(f"Analyzing {len(unique_hometowns)} total unique hometowns...")
    
    new_geocodes_since_save = 0
    for i, ht in enumerate(unique_hometowns, 1):
        # Skip if we already have the data in our cache
        if ht in geo_cache and geo_cache[ht].get('lat'):
            continue
            
        geo_cache[ht] = get_geocode_data(ht, api_key)
        if geo_cache[ht]:
            new_geocodes_since_save += 1
            
        if i % 10 == 0 or i == len(unique_hometowns):
            logging.info(f"  Geocoding progress: {i}/{len(unique_hometowns)} ({new_geocodes_since_save} new API calls in this session)...")
            
            # Save progress to the database every 20 successful API calls
            if new_geocodes_since_save >= 20:
                persist_registry_progress()
                new_geocodes_since_save = 0
    
    # Final geocoding persistence
    if new_geocodes_since_save > 0:
        persist_registry_progress()

    def enrich(row):
        geo = geo_cache.get(row['hometown'], {})
        ht_str = str(row['hometown']) if row['hometown'] else ""
        return pd.Series([
            geo.get('lat'), geo.get('lng'), geo.get('elevation'),
            # Clean the ID fallback generation by removing quotes
            geo.get('hometown_id', ht_str.lower().replace(' ', '-').replace(',', '').replace('.', '').replace("'", "").replace('"', '')),
            geo.get('region', determine_region(ht_str))
        ])

    logging.info("Enriching raw athlete data with geocoding results...")
    df_raw[['lat', 'lng', 'regional_elevation', 'hometown_id', 'region']] = df_raw.apply(enrich, axis=1)
    
    # 3. Aggregate into Hubs (NIL Compliant)
    df_hubs = df_raw.dropna(subset=['lat', 'lng']).groupby(
        ['hometown_id', 'region', 'sport', 'lat', 'lng', 'regional_elevation']
    ).agg(
        athlete_count=('athlete_id', 'count'),
        athlete_ids=('athlete_id', lambda x: ', '.join(x.astype(str)))
    ).reset_index().rename(columns={'sport': 'sport_name'})
    
    df_hubs['load_timestamp'] = pd.Timestamp.now(tz='UTC')

    # 4. Save to BigQuery
    table_ref = f"{project_id}.{dataset_id}.hometown_hubs"
    job_config = bigquery.LoadJobConfig(
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
        write_disposition="WRITE_TRUNCATE",
    )
    
    client.load_table_from_dataframe(df_hubs, table_ref, job_config=job_config).result()
    logging.info(f"Successfully processed {len(df_hubs)} sport-specific hubs into {table_ref}")

    # 5. Create a dedicated Geographic Summary Table (Regional Registry)
    # This deduplicates geography for the frontend map and provides total regional counts
    df_summary = df_raw.dropna(subset=['lat', 'lng']).groupby(
        ['hometown_id', 'region', 'lat', 'lng', 'regional_elevation']
    ).agg(
        total_athlete_count=('athlete_id', 'count'),
        sports=('sport', lambda x: [{"sport": s, "count": int(c)} for s, c in sorted(x.value_counts().items())])
    ).reset_index()
    
    df_summary['load_timestamp'] = pd.Timestamp.now(tz='UTC')

    summary_table_ref = f"{project_id}.{dataset_id}.regional_hubs_summary"
    summary_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("hometown_id", "STRING"),
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
        ],
        write_disposition="WRITE_TRUNCATE",
    )
    
    client.load_table_from_dataframe(df_summary, summary_table_ref, job_config=summary_config).result()
    logging.info(f"Successfully created geographic summary table: {summary_table_ref}")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT: raise ValueError("GOOGLE_CLOUD_PROJECT not set.")
    process_geocoding_service(PROJECT, "team_usa_data")