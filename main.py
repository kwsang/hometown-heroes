import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from services.gemini_service import GeminiNarrativeService
from services.bigquery_service import BigQueryService
from services.frontend_service import render_landing_page, render_hub_detail_page
from services.map_service import render_hubs_page
from dotenv import load_dotenv

# Ensure environment variables are loaded before initializing services
load_dotenv()

app = FastAPI(title="Hometown Heroes API")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")

if not PROJECT_ID:
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")

gemini_engine = GeminiNarrativeService(project_id=PROJECT_ID)
data_engine = BigQueryService(project_id=PROJECT_ID)

@app.get("/", response_class=HTMLResponse)
async def root():
    return render_landing_page()

@app.get("/health")
def health_check():
    return {"status": "healthy", "engine": "Hometown Heroes"}

@app.get("/hubs", response_class=HTMLResponse)
async def hubs_page():
    # Dynamically fetch hub locations from BigQuery
    hubs = data_engine.get_all_hubs()
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY",)
    return render_hubs_page(hubs, google_maps_api_key)

@app.get("/.well-known/appspecific/com.chrome.devtools.json")
async def silence_chrome_devtools():
    # This route exists purely to silence 404 logs from Chrome DevTools
    return {}

@app.get("/hubs/{hometown_id}", response_class=HTMLResponse)
async def hub_detail_page(hometown_id: str):
    try:
        # 1. Get Aggregate Data from BigQuery
        stats = data_engine.get_aggregate_hub_stats(hometown_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Hub not found")

        return render_hub_detail_page(hometown_id, stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/hubs/{hometown_id}/stats")
async def get_hub_stats(hometown_id: str):
    try:
        # Get Aggregate Data from BigQuery (Cached)
        stats = data_engine.get_aggregate_hub_stats(hometown_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Hub not found")
        return {
            "hub": hometown_id,
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/hubs/{hometown_id}/narrative")
async def get_hub_narrative(hometown_id: str):
    try:
        stats = data_engine.get_aggregate_hub_stats(hometown_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Hub not found")
        
        elevation = stats[0].get("regional_elevation", "Unknown") if stats else "Unknown"
        climate_mock = {
            "avg_elevation": f"{elevation}m" if elevation != "Unknown" else elevation,
            "notable_features": "Local terrain and climate conditions relevant to sport excellence."
        }

        narrative = await gemini_engine.generate_hub_narrative(hometown_id, stats, climate_mock)
        
        return {
            "narrative": narrative
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/hubs/{hometown_id}")
async def get_hub_details(hometown_id: str):
    try:
        # 1. Get Aggregate Data from BigQuery
        stats = data_engine.get_aggregate_hub_stats(hometown_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Hub not found")
        
        # Extract real elevation from BigQuery results if available to replace the mock
        elevation = stats[0].get("regional_elevation", "Unknown") if stats else "Unknown"
        
        climate_mock = {
            "avg_elevation": f"{elevation}m" if elevation != "Unknown" else elevation,
            "notable_features": "Local terrain and climate conditions relevant to sport excellence."
        }

        narrative = await gemini_engine.generate_hub_narrative(hometown_id, stats, climate_mock)
        
        return {
            "hub": hometown_id,
            "statistics": stats,
            "narrative": narrative
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))