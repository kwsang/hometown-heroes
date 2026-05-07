import os
import logging
from dotenv import load_dotenv
from services.hub_service import HubService

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    MAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
    
    if not PROJECT: raise ValueError("GOOGLE_CLOUD_PROJECT not set.")
    if not MAPS_KEY: raise ValueError("GOOGLE_MAPS_API_KEY not set.")

    hub_service = HubService(PROJECT, MAPS_KEY)
    hub_service.process_hubs("team_usa_data")