from typing import List, Dict, Any
import logging
from services.gemini_service import GeminiNarrativeService
from services.bigquery_service import BigQueryService

class AIInsightsService:
    """
    Service to handle the logic for generating and rendering AI-powered regional insights.
    """
    def __init__(self, project_id: str):
        self.gemini = GeminiNarrativeService(project_id=project_id)
        self.bigquery = BigQueryService(project_id=project_id)

    async def get_narrative(self, hometown_id: str) -> str:
        """Fetch stats and generate a narrative for a specific hub."""
        # 1. Check BigQuery Cache First
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
        
        # 2. Generate if not cached
        narrative = await self.gemini.generate_hub_narrative(hometown_id, stats, climate_mock)
        
        # 3. Persist to cache for future requests
        try:
            self.bigquery.update_hub_narrative(hometown_id, narrative)
        except Exception as e:
            logging.error(f"Cache write failed for {hometown_id}: {e}")
        
        return narrative

def get_insights_html() -> str:
    """Returns the HTML structure for the AI Insights section in the drawer."""
    return """
                <div id="narrative-container" class="bg-blue-50 p-6 rounded-2xl border border-blue-100 mb-8">
                    <h3 class="text-sm font-bold text-blue-900 mb-2 flex items-center">
                        <span class="mr-2">✨</span> AI Insights
                    </h3>
                    <p id="narrative-text" class="text-blue-900 leading-relaxed italic opacity-80 text-sm animate-pulse">
                        Generating regional narrative...
                    </p>
                </div>
    """

def get_insights_js(api_key: str) -> str:
    """
    Returns the JS logic to fetch and display the hub narrative.
    Assumes 'hubId' is available in the parent JavaScript scope.
    """
    return f"""
                // Fetch narrative lazily to prioritize UI responsiveness
                fetch(`/api/v1/hubs/${{hubId}}/narrative`, {{
                    headers: {{ 'Authorization': `Bearer {api_key}` }} 
                }})
                    .then(res => res.json())
                    .then(data => {{
                        const narrativeEl = document.getElementById('narrative-text');
                        if (narrativeEl) {{
                            narrativeEl.classList.remove('animate-pulse');
                            narrativeEl.innerHTML = `"\${{data.narrative}}"`;
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