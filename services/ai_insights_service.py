from typing import List, Dict, Any
import logging
from .gemini_service import GeminiNarrativeService
from .bigquery_service import BigQueryService
from .firestore_service import FirestoreService

class AIInsightsService:
    """
    Service to handle the logic for generating and rendering AI-powered regional insights.
    """
    def __init__(self, project_id: str):
        self.gemini = GeminiNarrativeService(project_id=project_id)
        self.bigquery = BigQueryService(project_id=project_id)
        self.firestore = FirestoreService(project_id=project_id)

    async def get_narrative(self, hometown_id: str) -> str:
        """Fetch stats and generate a narrative for a specific hub."""
        # 1. Check Serving Layer (Firestore) first for lowest latency
        hub_doc = self.firestore.get_hub(hometown_id)
        if hub_doc and hub_doc.get("narrative"):
            return hub_doc["narrative"]

        # 2. Fallback to BigQuery Cache
        cached_narrative = self.bigquery.get_cached_narrative(hometown_id)
        if cached_narrative:
            return cached_narrative

        stats = self.bigquery.get_aggregate_hub_stats(hometown_id)
        if not stats:
            return "Regional data is currently being indexed."
            
        elevation = stats[0].get("regional_elevation", "Unknown") if stats else "Unknown"
        climate_mock = {
            "avg_elevation": f"{elevation}m" if elevation != "Unknown" else elevation,
            "notable_features": "Local terrain and climate conditions relevant to sport excellence."
        }
        
        # 3. Generate if not cached anywhere
        narrative = await self.gemini.generate_hub_narrative(hometown_id, stats, climate_mock)
        
        # 4. Persist to cache (BigQuery) and Serving Layer (Firestore)
        try:
            self.bigquery.update_hub_narrative(hometown_id, narrative)
            self.firestore.update_field(hometown_id, "narrative", narrative)
        except Exception as e:
            logging.error(f"Cache write failed for {hometown_id}: {e}")
        
        return narrative

def get_insights_html() -> str:
    """Returns the HTML structure for the AI Insights section in the drawer."""
    return """
                <div id="narrative-container" class="bg-blue-50 p-4 rounded-2xl border border-blue-100 mb-4">
                    <h3 class="text-sm font-bold text-blue-900 mb-2 flex items-center">
                        <span class="mr-2">✨</span> AI Insights
                    </h3>
                    <p id="narrative-text" class="text-blue-900 leading-relaxed opacity-80 text-sm animate-pulse">
                        Generating regional narrative...
                    </p>
                </div>
    """

def get_insights_js(api_key: str) -> str:
    """
    Returns the JS logic to fetch and display the hub narrative.
    Assumes 'hubId' is available in the parent JavaScript scope.
    """
    return rf"""
                // Fetch narrative lazily to prioritize UI responsiveness
                fetch(`/api/v1/hubs/${{encodeURIComponent(hubId)}}/narrative`, {{
                    headers: {{ 'Authorization': `Bearer {api_key}` }} 
                }})
                    .then(res => res.json())
                    .then(data => {{
                        // Only update the narrative if the user hasn't switched to another hub
                        if (activeHubId !== hubId) return;

                        const narrativeEl = document.getElementById('narrative-text');
                        if (narrativeEl) {{
                            narrativeEl.classList.remove('animate-pulse');
                            narrativeEl.innerHTML = data.narrative;
                        }}
                    }})
                    .catch(err => {{
                        const narrativeEl = document.getElementById('narrative-text');
                        if (narrativeEl) {{
                            narrativeEl.classList.remove('animate-pulse');
                            narrativeEl.innerText = "Regional insights are currently unavailable.";
                        }}
                    }});
    """