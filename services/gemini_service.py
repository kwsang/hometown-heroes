import vertexai
import logging
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold
from typing import List, Dict, Any
from google.api_core import exceptions as google_exceptions

class GeminiNarrativeService:
    def __init__(self, project_id: str, location: str = "us-central1"):
        vertexai.init(project=project_id, location=location)
        
        # Passing instructions in the constructor ensures they are treated as system instructions
        system_instruction = (
            "You are the narrative engine for 'Hometown Heroes'. "
            "Your goal is to explain how American geography and climate foster Team USA excellence. "
            "\n\nSTRICT RULES:\n"
            "1. PRIVACY: No individual Names, Images, or Likeness (NIL). Never mention specific names or scoring results.\n"
            "2. AGGREGATION: Only discuss communities and hubs (e.g., 'A significant group of athletes from this region').\n"
            "3. TERMINOLOGY: Refer to the Games exactly as 'Olympic Games [City] [Year]' or 'Paralympic Winter Games [City] [Year]'.\n"
            "4. NO 'PAST': Never use 'former' or 'past' Olympian/Paralympian. They are always Olympians/Paralympians.\n"
            "5. CAUSATION: Use conditional phrasing like 'could help find' or 'suggests a link'. Do not state geography is the cause.\n"
            "6. HUB LOGIC: Focus on why this specific region is a hub for certain sports based on terrain or climate.\n"
            "7. EMPHASIS: Use HTML <strong> tags for bolding sport names or key geographical features. Ensure sport names are in Title Case, not ALL CAPS."
        )
        
        # Using Gemini 2.5 Pro as specified in project requirements
        self.model = GenerativeModel("gemini-2.5-pro", system_instruction=system_instruction) # Consider pinning a specific version

    async def generate_hub_narrative(self, region_name: str, stats: List[Dict[str, Any]], climate_data: Dict[str, Any]):
        """
        Generates a compliant, inspiring narrative about a regional hub.
        """
        prompt = (
            f"Analyze the {region_name} hub using this data:\n"
            f"- Aggregate Sport Stats: {stats}\n"
            f"- Climate/Geography: {climate_data}\n\n"
            "Generate a narrative that connects the environment to the sports presence, "
            "emphasizing the collective power of Team USA in this area."
        )
        
        # Configure safety settings
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        }

        try:
            response = await self.model.generate_content_async(
                prompt,
                safety_settings=safety_settings
            )
        except google_exceptions.ResourceExhausted:
            logging.error(f"Gemini Rate Limit Exceeded for hub: {region_name}")
            return "The regional narrative is currently unavailable due to high demand. Please try again in a few moments."
        except google_exceptions.DeadlineExceeded:
            logging.error(f"Gemini Timeout for hub: {region_name}")
            return "Narrative generation timed out. Local geographic insights are still being processed."
        except google_exceptions.Forbidden as e:
            logging.error(f"Gemini Permission Denied: {e}. Ensure 'Vertex AI User' role is assigned to the service account.")
            return "Regional insights are restricted due to system permissions."
        except Exception as e:
            logging.error(f"Unexpected AioRpcError in Gemini service: {e}", exc_info=True)
            return "A localized narrative for this region is currently being synthesized based on community athletic history."
        
        # Check for prompt feedback that might indicate safety blocks
        # Safely handle empty or blocked responses
        if response.candidates and response.candidates[0].content.parts:
            return response.text
        
        return "A localized narrative for this region is currently being synthesized based on community athletic history."