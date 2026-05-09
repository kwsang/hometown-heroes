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
        # Extreme performance: In-memory cache for the most popular hubs
        self._memory_cache = {}

    async def get_narrative(self, hometown_id: str) -> str:
        """Fetch stats and generate a narrative for a specific hub."""
        # 1. Check Serving Layer (Firestore) first for lowest latency
        # 0. Check process memory (Fastest - 0ms network latency)
        if hometown_id in self._memory_cache:
            return self._memory_cache[hometown_id]

        # 1. Check Serving Layer (Firestore) for low latency (~20-50ms)
        hub_doc = self.firestore.get_hub(hometown_id)
        if hub_doc and hub_doc.get("narrative"):
            self._memory_cache[hometown_id] = hub_doc["narrative"]
            return hub_doc["narrative"]

        # 2. Generate if not cached in Firestore (Medium - 2-5s)
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
            logging.info(f"Storing generated narrative for {hometown_id} to BigQuery and Firestore...")
            self.bigquery.update_hub_narrative(hometown_id, narrative)
            self.firestore.update_field(hometown_id, "narrative", narrative)
            self._memory_cache[hometown_id] = narrative
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
                // 1. Check browser session storage first
                const sessionKey = `narrative_${{hubId}}`;
                const cached = sessionStorage.getItem(sessionKey);
                if (cached) {{
                    const narrativeEl = document.getElementById('narrative-text');
                    if (narrativeEl) narrativeEl.innerHTML = cached;
                    return;
                }}

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
                            const formattedNarrative = data.narrative;
                            narrativeEl.innerHTML = formattedNarrative;
                            
                            // Populate the global cache
                            narrativeCache[hubId] = formattedNarrative;
                            // Populate browser session storage
                            sessionStorage.setItem(sessionKey, formattedNarrative);
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