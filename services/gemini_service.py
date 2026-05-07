import vertexai
from vertexai.generative_models import GenerativeModel, HarmCategory, HarmBlockThreshold
from typing import List, Dict, Any

class GeminiNarrativeService:
    def __init__(self, project_id: str, location: str = "us-central1"):
        vertexai.init(project=project_id, location=location)
        # Using Gemini 2.5 Pro as specified in project requirements
        self.model = GenerativeModel("gemini-2.5-pro")
        
        # These instructions ensure the AI adheres to the strict hackathon rules
        self.system_instruction = (
            "You are the narrative engine for 'Hometown Heroes'. "
            "Your goal is to explain how American geography and climate foster Team USA excellence. "
            "\n\nSTRICT RULES:\n"
            "1. PRIVACY: No individual Names, Images, or Likeness (NIL). Never mention specific names or scoring results.\n"
            "2. AGGREGATION: Only discuss communities and hubs (e.g., 'A significant group of athletes from this region').\n"
            "3. TERMINOLOGY: Refer to the Games exactly as 'Olympic Games [City] [Year]' or 'Paralympic Winter Games [City] [Year]'.\n"
            "4. NO 'PAST': Never use 'former' or 'past' Olympian/Paralympian. They are always Olympians/Paralympians.\n"
            "5. CAUSATION: Use conditional phrasing like 'could help find' or 'suggests a link'. Do not state geography is the cause.\n"
            "6. HUB LOGIC: Focus on why this specific region is a hub for certain sports based on terrain or climate."
        )

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
        
        # High safety settings to ensure no NIL or PII is hallucinated
        safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        }

        response = await self.model.generate_content_async(
            [self.system_instruction, prompt],
            safety_settings=safety_settings
        )
        return response.text