import os
import logging
from typing import Annotated, Dict, List
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import FastAPI, HTTPException, Depends, Request, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
import google.auth
from services.gemini_service import GeminiNarrativeService
from services.bigquery_service import BigQueryService
from services.frontend_service import render_landing_page, render_hub_detail_page
from services.map_service import render_hubs_page
from services.ai_insights_service import AIInsightsService
from services.image_generation_service import ImageGenerationService

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # This is expected in Cloud Run environments where dotenv isn't installed
    logging.info("python-dotenv not found; skipping load_dotenv.")

# --- Security: API Key Authentication ---
# In a real-world scenario, you'd use a more robust auth mechanism (e.g., OAuth2, JWT)
# For simple API key protection, this is a basic example.
API_KEY = (os.getenv("API_KEY") or "").strip("'\"")

if not API_KEY:
    logging.warning("API_KEY environment variable is not set or empty. API endpoints will be inaccessible.")

def verify_api_key(auth: Annotated[HTTPAuthorizationCredentials, Depends(HTTPBearer())]):
    if auth.credentials != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return auth

# --- Simple In-Memory Rate Limiting ---
# Tracks hits per IP address in a 1-minute window
request_history: Dict[str, List[datetime]] = defaultdict(list)

def rate_limiter(request: Request):
    client_ip = request.client.host
    now = datetime.now()
    
    # Cleanup: Remove requests older than 60 seconds
    request_history[client_ip] = [t for t in request_history[client_ip] if now - t < timedelta(minutes=1)]
    
    if len(request_history[client_ip]) > 30: # Limit to 30 requests per minute per IP
        raise HTTPException(status_code=429, detail="Too many requests. Please try again in a minute.")
    
    request_history[client_ip].append(now)

# --- End Security ---

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Hometown Heroes API")

# --- Security: Content Security Policy (CSP) ---
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Define a CSP that allows Google Maps, Google Fonts, and Base64 images from Vertex AI
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://maps.googleapis.com https://*.google.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://maps.googleapis.com; "
        "img-src 'self' data: https://storage.googleapis.com https://maps.gstatic.com https://*.googleapis.com https://*.google.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "frame-src 'self' https://*.google.com; "
        "connect-src 'self' https://*.googleapis.com https://*.google.com"
    )
    response.headers["Content-Security-Policy"] = csp
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


# --- Hardening: Restrict CORS Origins ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure required directories exist to avoid FastAPI startup failure
for doc_dir in ["img", "static"]:
    if not os.path.exists(doc_dir):
        os.makedirs(doc_dir)

logging.info(f"Allowed Origins: {ALLOWED_ORIGINS}")

# Mount the static images directory so the browser can access the favicon
app.mount("/img", StaticFiles(directory="img"), name="img")

# Mount the static directory for CSS and other assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Route to solve 404 favicon.ico ---
@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse(os.path.join("img", "favicon.ico"))

# Attempt to get the Project ID from the environment, falling back to 
# Google's auth discovery (which works automatically on Cloud Run)
PROJECT_ID = (os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or "").strip("'\"")

if not PROJECT_ID:
    try:
        _, PROJECT_ID = google.auth.default()
        logging.info(f"Auto-discovered Project ID: {PROJECT_ID}")
    except Exception as e:
        logging.error(f"Failed to auto-discover Google Cloud Project ID: {e}")

if not PROJECT_ID:
    logging.error("CRITICAL: GOOGLE_CLOUD_PROJECT is missing.")
    raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")

gemini_engine = GeminiNarrativeService(project_id=PROJECT_ID)
data_engine = BigQueryService(project_id=PROJECT_ID)
insights_engine = AIInsightsService(project_id=PROJECT_ID)
image_engine = ImageGenerationService(project_id=PROJECT_ID)

@app.get("/", response_class=HTMLResponse)
async def root():
    return render_landing_page()

@app.get("/health")
def health_check():
    return {"status": "healthy", "engine": "Hometown Heroes"}

@app.get("/hubs", response_class=HTMLResponse)
async def hubs_page():
    try:
        # Dynamically fetch hub locations from BigQuery
        hubs = data_engine.get_all_hubs()
        
        if not hubs:
            logging.warning("No hubs found in BigQuery. Ensure ETL processing has run.")
            # Optional: Return a specific "No Data" page instead of a 500
        
        google_maps_api_key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip("'\"")

        if not google_maps_api_key:
            logging.error("GOOGLE_MAPS_API_KEY environment variable is missing. Maps will not initialize.")

        return render_hubs_page(hubs, google_maps_api_key, API_KEY)
    except google.api_core.exceptions.NotFound:
        logging.error("BigQuery Table 'regional_hubs_summary' not found. Have you run the processing scripts?")
        raise HTTPException(status_code=503, detail="Database table not initialized. Please run the data ingestion pipeline.")
    except google.api_core.exceptions.Forbidden as e:
        logging.error(f"Permission denied accessing BigQuery: {e}")
        raise HTTPException(status_code=403, detail="The service account does not have permission to read from BigQuery.")
    except Exception as e:
        logging.error(f"Unexpected error loading hubs page: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load regional hubs data.")

@app.get("/.well-known/appspecific/com.chrome.devtools.json", include_in_schema=False)
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

        return render_hub_detail_page(hometown_id, stats, api_key=API_KEY)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/api/v1/hubs/{hometown_id}/stats", 
    dependencies=[Depends(verify_api_key), Depends(rate_limiter)]
)
async def get_hub_stats(
    hometown_id: Annotated[str, Path(pattern="^[a-z0-9\-]+$")]
):
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

@app.get(
    "/api/v1/hubs/{hometown_id}/narrative", 
    dependencies=[Depends(verify_api_key), Depends(rate_limiter)]
)
async def get_hub_narrative(
    hometown_id: Annotated[str, Path(pattern="^[a-z0-9\-]+$")]
):
    try:
        # Use the specialized AI Insights service to handle narrative generation
        narrative = await insights_engine.get_narrative(hometown_id)
        return {
            "narrative": narrative
        }
    except Exception as e:
        logging.error(f"Narrative endpoint failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get(
    "/api/v1/hubs/{hometown_id}/image", 
    dependencies=[Depends(verify_api_key), Depends(rate_limiter)]
)
async def get_hub_image(
    hometown_id: Annotated[str, Path(pattern="^[a-z0-9\-]+$")], 
    pretty_name: str, 
    region: str
):
    try:
        base64_image = await image_engine.get_hub_image(hometown_id, pretty_name, region)
        if not base64_image:
             raise HTTPException(status_code=404, detail="Image generation failed")
        return {
            "image_data": base64_image
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Image endpoint failure: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/hubs/{hometown_id}", dependencies=[Depends(verify_api_key)]) # Protect this endpoint
async def get_hub_details(hometown_id: str):
    try:
        stats = data_engine.get_aggregate_hub_stats(hometown_id)
        if not stats:
            raise HTTPException(status_code=404, detail="Hub not found")
        narrative = await insights_engine.get_narrative(hometown_id)
        return {
            "hub": hometown_id,
            "statistics": stats,
            "narrative": narrative
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))