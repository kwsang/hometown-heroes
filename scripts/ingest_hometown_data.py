import os
import json
import re
import logging
import pandas as pd
from google.cloud import bigquery
import requests
from bs4 import BeautifulSoup
import time
import vertexai
from vertexai.generative_models import GenerativeModel

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def crawl_hometown(athlete_name: str, project_id: str = None) -> str:
    """
    Attempts to retrieve an athlete's hometown from their Team USA profile.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}

    def extract_from_soup(soup):
        # Team USA profiles often store hometown in a specific metadata div or span
        hometown_tag = soup.find('div', string=re.compile('Hometown', re.I))
        if hometown_tag and hometown_tag.find_next_sibling():
            return hometown_tag.find_next_sibling().get_text(strip=True)
        
        # Fallback: check for common bio patterns
        bio_section = soup.find('div', class_='athlete-profile__bio')
        if bio_section:
            match = re.search(r'Hometown:\s*([^<]+)', str(bio_section))
            if match:
                return match.group(1).strip()
        return None

    # Create a URL slug: "John Doe" -> "john-doe"
    slug = re.sub(r'[^a-z0-9]+', '-', athlete_name.lower()).strip('-')
    url = f"https://www.teamusa.com/athletes/{slug}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            hometown = extract_from_soup(BeautifulSoup(response.text, 'html.parser'))
            if hometown:
                return hometown

        # Fallback: Query the search page as requested
        search_query = re.sub(r'[^a-z0-9]+', '-', athlete_name.lower()).strip('-')
        search_url = f"https://www.teamusa.com/search?q={search_query}"
        logging.info(f"Direct lookup failed for {athlete_name}. Attempting site search: {search_url}")
        
        search_response = requests.get(search_url, headers=headers, timeout=10)
        if search_response.status_code == 200:
            search_soup = BeautifulSoup(search_response.text, 'html.parser')
            # Find the first link that looks like a profile link
            profile_link = search_soup.find('a', href=re.compile(r'/(profiles|athletes)/'))
            if profile_link:
                profile_url = profile_link['href']
                if not profile_url.startswith('http'):
                    profile_url = f"https://www.teamusa.com{profile_url}"
                
                logging.info(f"Found profile via search: {profile_url}")
                profile_response = requests.get(profile_url, headers=headers, timeout=10)
                if profile_response.status_code == 200:
                    return extract_from_soup(BeautifulSoup(profile_response.text, 'html.parser'))

    except Exception as e:
        logging.warning(f"Could not crawl profile for {athlete_name}: {e}")

    # Final Fallback: Ask Gemini
    if project_id:
        logging.info(f"Web crawl failed for {athlete_name}. Falling back to Gemini reasoning.")
        try:
            # Using gemini-2.5-pro as per project requirements
            model = GenerativeModel("gemini-2.5-pro")
            prompt = f"What is the official hometown (City, State) of the Team USA Olympian/Paralympian {athlete_name}? Return ONLY the City, State string or 'null' if unknown."
            response = model.generate_content(prompt)
            if response.text and "null" not in response.text.lower():
                return response.text.strip()
        except Exception as e:
            logging.warning(f"Gemini fallback failed for {athlete_name}: {e}")

    return None

def get_geocode_data(hometown: str, google_maps_api_key: str) -> dict:
    """
    Fetches geocoding and elevation data for a given hometown using Google Maps APIs.
    Returns a dictionary with 'lat', 'lng', 'elevation', and 'region_id'.
    """
    if not hometown:
        return {}

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

def generate_nil_safe_id(athlete: dict, seen_ids: set) -> str:
    """
    Generates an NIL-safe identifier: <First Initial><Last Initial><Year First Competed>.
    Handles duplicates by appending a counter.
    """
    name = athlete.get('name') or "Unknown"
    years = athlete.get('participation_years') or []

    # 1. Extract Initials (First and Last)
    name_parts = re.sub(r'[^a-zA-Z\s]', '', name).split()
    initials = (name_parts[0][0] if len(name_parts) > 0 else "U") + \
               (name_parts[-1][0] if len(name_parts) > 1 else "")
    initials = initials.upper()

    # 2. Extract Earliest Year
    found_years = []
    for y_str in years:
        found_years.extend([int(y) for y in re.findall(r'\d{4}', str(y_str))])
    first_year = str(min(found_years)) if found_years else "0000"

    base_id = f"{initials}{first_year}"
    final_id = base_id
    counter = 1
    while final_id in seen_ids:
        counter += 1
        final_id = f"{base_id}-{counter}"
    
    seen_ids.add(final_id)
    return final_id

def ingest_hometown_data(project_id: str, dataset_id: str, table_id: str, olympians_data: list, update_file_path: str = None):
    """
    Demonstrates populating the Hometown Heroes database with enriched,
    aggregated athlete data.

    Args:
        project_id: The Google Cloud project ID.
        dataset_id: The BigQuery dataset ID.
        table_id: The BigQuery table ID.
        olympians_data: A list of dictionaries, where each dict represents an Olympian
                        with at least 'name', 'hometown', and 'sport'.
        update_file_path: Optional path to update the source JSON with crawled hometowns.
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    # Initialize Vertex AI once for the duration of the ingestion process
    try:
        vertexai.init(project=project_id)
    except Exception as e:
        logging.warning(f"Failed to initialize Vertex AI: {e}")

    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not google_maps_api_key:
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable not set.")

    # 1. Process each athlete: ID generation, Crawling, and Geocoding
    updated = False
    seen_ids = set()
    geocode_cache = {} # Avoid redundant API calls for the same hometown

    for athlete in olympians_data:
        athlete_name = athlete.get('name')
        # a. Ensure Hometown exists
        if not athlete.get('hometown'):
            logging.info(f"Missing hometown for {athlete_name}. Attempting to crawl...")
            hometown = crawl_hometown(athlete_name, project_id=project_id)
            if hometown:
                athlete['hometown'] = hometown
                updated = True
                logging.info(f"Successfully updated '{athlete_name}' with location: {hometown}")
            else:
                logging.warning(f"Could not retrieve hometown for {athlete_name}. Proceeding with null value.")
        
        # b. Generate NIL-Safe ID
        athlete['athlete_id'] = generate_nil_safe_id(athlete, seen_ids)

        # c. Geocode immediately (with caching)
        hometown = athlete.get('hometown')
        if hometown and hometown not in geocode_cache:
            geocode_cache[hometown] = get_geocode_data(hometown, google_maps_api_key)
        
        geo = geocode_cache.get(hometown, {})
        athlete['lat'] = geo.get('lat')
        athlete['lng'] = geo.get('lng')
        athlete['regional_elevation'] = geo.get('elevation')
        
        hometown_str = str(hometown) if hometown else ""
        athlete['region_id'] = geo.get('region_id', hometown_str.lower().replace(' ', '-').replace(',', '').replace('.', ''))

    if updated and update_file_path:
        with open(update_file_path, 'w', encoding='utf-8') as f:
            json.dump(olympians_data, f, indent=4)
        logging.info(f"Local JSON file '{update_file_path}' has been updated with new location data.")

    # Add ingestion timestamp for auditability
    load_timestamp = pd.Timestamp.now(tz='UTC')

    df_raw = pd.DataFrame(olympians_data)
    
    # Aggregation (Enforcing NIL Compliance): Group by region, sport, and geographic data.
    # athlete_ids now contains the safe identifiers (e.g. MP2004)
    df_aggregated = df_raw.groupby(['region_id', 'sport', 'lat', 'lng', 'regional_elevation']).agg(
        athlete_count=('athlete_id', 'count'),
        athlete_ids=('athlete_id', lambda x: ', '.join(x.astype(str)))
    ).reset_index()

    # Rename for BigQuery schema
    df_aggregated = df_aggregated.rename(columns={'sport': 'sport_name'})
    
    # Filter out rows where geocoding failed (lat/lng are None) if desired, or handle them
    df_aggregated = df_aggregated.dropna(subset=['lat', 'lng'])
    df_aggregated['load_timestamp'] = load_timestamp

    # Load to BigQuery
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
        write_disposition="WRITE_TRUNCATE", # Overwrite the table on each run
    )

    job = client.load_table_from_dataframe(df_aggregated, table_ref, job_config=job_config)
    job.result()  # Wait for the job to complete

    print(f"Successfully loaded {len(df_aggregated)} hubs into {table_ref}")
    print(f"Example aggregated data:\n{df_aggregated.head()}")

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set. Please set it to your Google Cloud Project ID.")

    # Example: Processing a specific JSON file from the parser output
    # Updated to look for the provided Table Tennis sample or fallback to Baseball
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_DIR = os.path.join(SCRIPT_DIR, "resources", "output")
    
    json_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')]
    
    if json_files:
        target_file = os.path.join(OUTPUT_DIR, json_files[0]) # Process the first found file
        print(f"Processing {target_file}...")
        with open(target_file, "r", encoding="utf-8") as f:
            athletes = json.load(f)
        
        ingest_hometown_data(PROJECT, "team_usa_data", "hometown_hubs", athletes, update_file_path=target_file)
    else:
        print(f"No JSON files found in {OUTPUT_DIR}")