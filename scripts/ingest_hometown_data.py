import os
import pandas as pd
from google.cloud import bigquery
import requests
import time

def get_geocode_data(hometown: str, google_maps_api_key: str) -> dict:
    """
    Fetches geocoding and elevation data for a given hometown using Google Maps APIs.
    Returns a dictionary with 'lat', 'lng', 'elevation', and 'region_id'.
    """
    base_url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": hometown,
        "key": google_maps_api_key
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status() # Raise an exception for HTTP errors
        data = response.json()

        if data['status'] == 'OK' and data['results']:
            location = data['results'][0]['geometry']['location']
            lat = location['lat']
            lng = location['lng']
            
            # Fetch elevation
            elevation_url = "https://maps.googleapis.com/maps/api/elevation/json"
            elevation_params = {
                "locations": f"{lat},{lng}",
                "key": google_maps_api_key
            }
            elevation_response = requests.get(elevation_url, params=elevation_params)
            elevation_response.raise_for_status()
            elevation_data = elevation_response.json()
            elevation = elevation_data['results'][0]['elevation'] if elevation_data['status'] == 'OK' and elevation_data['results'] else None

            # Simple region_id generation (can be improved with place_id or more robust logic)
            region_id = hometown.lower().replace(' ', '-').replace(',', '').replace('.', '')

            return {'lat': lat, 'lng': lng, 'elevation': elevation, 'region_id': region_id}
        else:
            print(f"Geocoding failed for '{hometown}': {data.get('status')}")
            return {}
    except requests.exceptions.RequestException as e:
        print(f"API request failed for '{hometown}': {e}")
        return {}
    except Exception as e:
        print(f"An unexpected error occurred for '{hometown}': {e}")
        return {}

def ingest_hometown_data(project_id: str, dataset_id: str, table_id: str, olympians_data: list):
    """
    Demonstrates populating the Hometown Heroes database with enriched,
    aggregated athlete data.

    Args:
        project_id: The Google Cloud project ID.
        dataset_id: The BigQuery dataset ID.
        table_id: The BigQuery table ID.
        olympians_data: A list of dictionaries, where each dict represents an Olympian
                        with at least 'athlete_id', 'hometown', and 'sport'.
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    df_raw = pd.DataFrame(olympians_data)

    # Get unique hometowns for geocoding
    unique_hometowns = df_raw['hometown'].unique()

    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set. Please set it with your Google Maps API key.")

    # Geocode all unique hometowns and store results
    geocoded_results = {}
    for hometown in unique_hometowns:
        # Add a small delay to respect API rate limits if needed
        # time.sleep(0.1) 
        geocoded_results[hometown] = get_geocode_data(hometown, google_maps_api_key)

    def enrich_row_with_geocode(row):
        geo = geocoded_results.get(row['hometown'], {})
        # Provide default/None for un-geocoded hometowns to avoid errors
        return pd.Series([
            geo.get('lat'),
            geo.get('lng'),
            geo.get('elevation'),
            geo.get('region_id', row['hometown'].lower().replace(' ', '-').replace(',', '').replace('.', '')) # Fallback region_id
        ])

    df_raw[['lat', 'lng', 'regional_elevation', 'region_id']] = df_raw.apply(enrich_row_with_geocode, axis=1)

    # Aggregation (Enforcing NIL Compliance): Group by region, sport, and geographic data
    df_aggregated = df_raw.groupby(['region_id', 'sport', 'lat', 'lng', 'regional_elevation']).agg(
        athlete_count=('athlete_id', 'count')
    ).reset_index()

    # Rename for BigQuery schema
    df_aggregated = df_aggregated.rename(columns={'sport': 'sport_name'})
    
    # Filter out rows where geocoding failed (lat/lng are None) if desired, or handle them
    df_aggregated = df_aggregated.dropna(subset=['lat', 'lng'])

    # Load to BigQuery
    job_config = bigquery.LoadJobConfig(
        schema=[
            bigquery.SchemaField("region_id", "STRING"),
            bigquery.SchemaField("sport_name", "STRING"),
            bigquery.SchemaField("lat", "FLOAT"),
            bigquery.SchemaField("lng", "FLOAT"),
            bigquery.SchemaField("regional_elevation", "FLOAT"),
            bigquery.SchemaField("athlete_count", "INTEGER"),
        ],
        write_disposition="WRITE_TRUNCATE", # Overwrite the table on each run
    )

    job = client.load_table_from_dataframe(df_aggregated, table_ref, job_config=job_config)
    job.result()  # Wait for the job to complete

    print(f"Successfully loaded {len(df_aggregated)} hubs into {table_ref}")
    print(f"Example aggregated data:\n{df_aggregated.head()}")

if __name__ == "__main__":
    # Example usage with mock data representing scraped Olympian profiles
    mock_olympians_data = [
        {"athlete_id": "A1", "hometown": "Colorado Springs, CO", "sport": "Cycling"},
        {"athlete_id": "A2", "hometown": "Colorado Springs, CO", "sport": "Cycling"},
        {"athlete_id": "A3", "hometown": "Park City, UT", "sport": "Skiing"},
        {"athlete_id": "A4", "hometown": "Chula Vista, CA", "sport": "Archery"},
        {"athlete_id": "A5", "hometown": "Colorado Springs, CO", "sport": "Swimming"},
        {"athlete_id": "A6", "hometown": "Gainesville, FL", "sport": "Swimming"},
    ]
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")
    ingest_hometown_data(PROJECT, "team_usa_data", "hometown_hubs", mock_olympians_data)