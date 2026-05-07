import os
import logging
import pandas as pd
from google.cloud import bigquery
import requests
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_geocode_data(hometown: str, api_key: str) -> dict:
    if not hometown: return {}
    api_key = api_key.strip("'").strip('"')
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    try:
        resp = requests.get(base_url, params={"address": hometown.strip(), "key": api_key})
        data = resp.json()
        if data['status'] == 'OK' and data['results']:
            loc = data['results'][0]['geometry']['location']
            lat, lng = loc['lat'], loc['lng']
            
            elev_resp = requests.get("https://maps.googleapis.com/maps/api/elevation/json", 
                                     params={"locations": f"{lat},{lng}", "key": api_key})
            elev_data = elev_resp.json()
            elevation = elev_data['results'][0]['elevation'] if elev_data['status'] == 'OK' else None
            
            region_id = hometown.lower().replace(' ', '-').replace(',', '').replace('.', '')
            return {'lat': lat, 'lng': lng, 'elevation': elevation, 'region_id': region_id}
    except Exception as e:
        logging.error(f"Geocoding error for {hometown}: {e}")
    return {}

def process_geocoding_service(project_id: str, dataset_id: str):
    client = bigquery.Client(project=project_id)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key: raise ValueError("GOOGLE_MAPS_API_KEY not set.")

    # 1. Fetch raw data
    query = f"SELECT athlete_id, sport, hometown FROM `{project_id}.{dataset_id}.athlete_locations`"
    df_raw = client.query(query).to_dataframe()
    
    if df_raw.empty:
        logging.info("No raw athlete data found to process.")
        return

    # 2. Geocode Unique Hometowns (Caching)
    unique_hometowns = df_raw['hometown'].dropna().unique()
    geo_cache = {ht: get_geocode_data(ht, api_key) for ht in unique_hometowns}
    
    def enrich(row):
        geo = geo_cache.get(row['hometown'], {})
        ht_str = str(row['hometown']) if row['hometown'] else ""
        return pd.Series([
            geo.get('lat'), geo.get('lng'), geo.get('elevation'),
            geo.get('region_id', ht_str.lower().replace(' ', '-').replace(',', '').replace('.', ''))
        ])

    df_raw[['lat', 'lng', 'regional_elevation', 'region_id']] = df_raw.apply(enrich, axis=1)
    
    # 3. Aggregate into Hubs (NIL Compliant)
    df_hubs = df_raw.dropna(subset=['lat', 'lng']).groupby(
        ['region_id', 'sport', 'lat', 'lng', 'regional_elevation']
    ).agg(
        athlete_count=('athlete_id', 'count'),
        athlete_ids=('athlete_id', lambda x: ', '.join(x.astype(str)))
    ).reset_index().rename(columns={'sport': 'sport_name'})
    
    df_hubs['load_timestamp'] = pd.Timestamp.now(tz='UTC')

    # 4. Save to BigQuery
    table_ref = f"{project_id}.{dataset_id}.hometown_hubs"
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("region_id", "STRING"),
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
    logging.info(f"Successfully processed {len(df_hubs)} hubs into {table_ref}")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT: raise ValueError("GOOGLE_CLOUD_PROJECT not set.")
    process_geocoding_service(PROJECT, "team_usa_data")