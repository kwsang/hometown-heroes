import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from services.gemini_service import GeminiNarrativeService
from services.bigquery_service import BigQueryService
from services.frontend_service import render_landing_page, render_hubs_page # Removed _get_head_html etc.

app = FastAPI(title="Hometown Heroes API")

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "your-project-id")

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
    # Mock data for demonstration - in production, this would be fetched from BigQuery,
    # likely including pre-calculated lat/lng for each hub.
    hubs = [
        {"id": "colorado-springs", "city": "Colorado Springs, CO", "lat": 38.8339, "lng": -104.8214, "description": "Known as Olympic City USA, this high-altitude hub is home to the USOPC and world-class training facilities."},
        {"id": "chula-vista", "city": "Chula Vista, CA", "lat": 32.6401, "lng": -117.0841, "description": "An elite training center environment with coastal conditions ideal for year-round outdoor sports excellence."},
        {"id": "lake-placid", "city": "Lake Placid, NY", "lat": 44.2795, "lng": -73.9799, "description": "A legendary winter sports hub in the Adirondacks, fostering generations of winter sports greatness."},
        {"id": "oklahoma-city", "city": "Oklahoma City, OK", "lat": 35.4676, "lng": -97.5164, "description": "A premier destination for rowing and paddle sports, leveraging unique river conditions for Team USA."},
        {"id": "park-city", "city": "Park City, UT", "lat": 40.6461, "lng": -111.4979, "description": "A hub for winter sports, offering high-altitude training and world-class facilities for skiing and snowboarding."},
        {"id": "gainesville", "city": "Gainesville, FL", "lat": 29.6516, "lng": -82.3248, "description": "Known for its aquatic sports programs and warm climate, ideal for year-round training."}
    ]
    
    # IMPORTANT: Replace 'YOUR_GOOGLE_MAPS_API_KEY' with your actual API key
    google_maps_api_key = os.getenv("GOOGLE_MAPS_API_KEY", "AIzaSyCn0x_YF7x68AJjD3sAwwKfadKK5CikZSk")
    return render_hubs_page(hubs, google_maps_api_key)

@app.get("/api/v1/hubs/{region_id}")
async def get_hub_details(region_id: str):
    try:
        # 1. Get Aggregate Data from BigQuery
        stats = data_engine.get_aggregate_hub_stats(region_id)
        
        # 2. Use Gemini to generate the contextual narrative
        # Real-world logic would involve fetching specific NOAA data for this region_id
        climate_mock = {
            "avg_elevation": "4,500ft",
            "notable_features": "High-altitude trails, consistent winter snowfall"
        }
        narrative = await gemini_engine.generate_hub_narrative(region_id, stats, climate_mock)
        
        return {
            "hub": region_id,
            "statistics": stats,
            "narrative": narrative
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))