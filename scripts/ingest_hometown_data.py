import os
import json
import re
import logging
import pandas as pd
from google.cloud import bigquery
from google.api_core.exceptions import NotFound
import requests
from bs4 import BeautifulSoup
import time
import vertexai
from vertexai.generative_models import GenerativeModel
from dotenv import load_dotenv

# Load environment variables from .env file at the start of the script
load_dotenv()

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

def ingest_hometown_data(project_id: str, dataset_id: str, olympians_data: list, update_file_path: str = None, location: str = "US"):
    """
    Demonstrates populating the Hometown Heroes database with enriched,
    aggregated athlete data.

    Args:
        project_id: The Google Cloud project ID.
        dataset_id: The BigQuery dataset ID.
        olympians_data: A list of dictionaries, where each dict represents an Olympian
                        with at least 'name', 'hometown', and 'sport'.
        update_file_path: Optional path to update the source JSON with crawled hometowns.
        location: The geographic location for the dataset (e.g., 'US' or 'EU').
    """
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.athlete_locations"

    # Define the schema once for table creation and streaming verification
    schema = [
        bigquery.SchemaField("athlete_id", "STRING"),
        bigquery.SchemaField("sport", "STRING"),
        bigquery.SchemaField("hometown", "STRING"),
        bigquery.SchemaField("load_timestamp", "TIMESTAMP"),
    ]

    # 1. Fetch existing IDs from BigQuery to enable resumption
    existing_ids = set()
    try:
        query_job = client.query(f"SELECT athlete_id FROM `{table_ref}`")
        results = query_job.result()
        existing_ids = {row.athlete_id for row in results}
        logging.info(f"Found {len(existing_ids)} existing records in BigQuery table. Resuming...")
    except Exception:
        logging.info("Target table not found or empty. Starting fresh.")

    # Initialize Vertex AI once for the duration of the ingestion process
    try:
        vertexai.init(project=project_id)
    except Exception as e:
        logging.warning(f"Failed to initialize Vertex AI: {e}")

    # Ensure the dataset exists
    dataset_ref = client.dataset(dataset_id)
    try:
        client.get_dataset(dataset_ref)
    except NotFound:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = location
        client.create_dataset(dataset)
        logging.info(f"Created new dataset: {dataset_id}")

    # Streaming inserts require the table to exist beforehand
    try:
        client.get_table(table_ref)
    except NotFound:
        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table)
        logging.info(f"Created table: {table_ref}")

    # 2. Process each athlete: ID generation and Crawling (only for new records)
    updated = False
    # Initialize seen_ids with existing IDs to avoid collisions when generating new ones
    seen_ids = set(existing_ids)
    batch_size = 10
    batch_to_insert = []
    
    for athlete in olympians_data:
        # a. Generate NIL-Safe ID first to check for existence
        # Note: If this is a repeat athlete, generate_nil_safe_id will yield the same ID
        athlete['athlete_id'] = generate_nil_safe_id(athlete, seen_ids)
        
        if athlete['athlete_id'] in existing_ids:
            continue

        athlete_name = athlete.get('name')
        if not athlete.get('hometown'):
            logging.info(f"Missing hometown for {athlete_name}. Attempting to crawl...")
            hometown = crawl_hometown(athlete_name, project_id=project_id)
            if hometown:
                athlete['hometown'] = hometown
                updated = True
                logging.info(f"Successfully updated '{athlete_name}' with location: {hometown}")
            else:
                logging.warning(f"Could not retrieve hometown for {athlete_name}. Proceeding with null value.")
        
        # 3. Batching Streaming Inserts for better performance
        row_to_insert = {
            "athlete_id": athlete['athlete_id'],
            "sport": athlete['sport'],
            "hometown": athlete.get('hometown'),
            "load_timestamp": pd.Timestamp.now(tz='UTC').isoformat()
        }
        batch_to_insert.append(row_to_insert)

        if len(batch_to_insert) >= batch_size:
            errors = client.insert_rows_json(table_ref, batch_to_insert)
            if errors:
                logging.error(f"Failed to insert batch: {errors}")
            else:
                logging.info(f"Successfully inserted batch of {len(batch_to_insert)} athletes into BigQuery.")
            batch_to_insert = []

    # Insert any remaining athletes in the last batch
    if batch_to_insert:
        errors = client.insert_rows_json(table_ref, batch_to_insert)
        if errors:
            logging.error(f"Failed to insert final batch: {errors}")
        else:
            logging.info(f"Successfully inserted final batch of {len(batch_to_insert)} athletes.")

    if updated and update_file_path:
        with open(update_file_path, 'w', encoding='utf-8') as f:
            json.dump(olympians_data, f, indent=4)
        logging.info(f"Local JSON file '{update_file_path}' has been updated with new location data.")

    logging.info("Ingestion process completed.")

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
        
        ingest_hometown_data(PROJECT, "team_usa_data", athletes, update_file_path=target_file)
    else:
        print(f"No JSON files found in {OUTPUT_DIR}")