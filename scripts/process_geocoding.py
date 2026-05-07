import os
import sys
import logging
from dotenv import load_dotenv

# Add the project root directory to the Python path to resolve the 'services' module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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