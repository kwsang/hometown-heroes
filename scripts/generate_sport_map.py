import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import List, Dict
from pypdf import PdfReader # Not strictly needed for the function, but useful for context/validation
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_sport_mapping(pdf_path: str, project_id: str, location: str = "us-central1") -> Dict[str, Dict]:
    """
    Uses Gemini to identify which pages contain which sports.
    Returns a mapping of sport names to 1-based page numbers.
    """
    vertexai.init(project=project_id, location=location)
    model = GenerativeModel("gemini-2.5-flash")
    
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    prompt = (
        "Thoroughly analyze this Team USA athlete directory to create a comprehensive sport-to-page index. "
        "Return a JSON mapping where keys are official sport names and values are objects containing:\n"
        "- 'pages': an array of ALL 1-based page numbers where that sport's athletes are listed.\n"
        "- 'first_athlete': the name of the first athlete listed in this section.\n"
        "- 'last_athlete': the name of the last athlete listed in this section (the athlete appearing immediately before the next section header).\n\n"
        "Important: Return athlete names EXACTLY as they appear in the text (including casing and punctuation).\n"
        "CRITICAL BOUNDARY RULES:\n"
        "1. Identify the exact page where a sport starts by looking for its primary section header. These headers are typically large and colored BLUE or RED.\n"
        "2. Identify the EXACT page where a sport ends. A sport ends ONLY when a NEW sport's header (Blue or Red) is visible. "
        "Do NOT let sport ranges overlap or spill into the next sport.\n"
        "3. Include EVERY page in the range. For example, if 'Baseball' is only on pages 2 and 3, "
        "the output MUST be [2, 3]. Do not hallucinate extra pages beyond the next section header."
    )
    
    response = model.generate_content([prompt, pdf_part], generation_config={"response_mime_type": "application/json"})
    raw_response_json = json.loads(response.text)
    print(f"Raw sport mapping response from Gemini: {json.dumps(raw_response_json, indent=2)}") # Log raw response
    
    # Ensure all page numbers are integers, as Gemini might sometimes return them as strings
    cleaned_sport_map = {}
    for sport, data in raw_response_json.items():
        page_list = data.get('pages', []) if isinstance(data, dict) else []
        cleaned_page_list = []
        for page_num in page_list:
            try:
                cleaned_page_list.append(int(page_num))
            except (ValueError, TypeError):
                print(f"Warning: Non-integer page number found for sport '{sport}': '{page_num}'. Skipping or attempting conversion.")
        
        cleaned_sport_map[sport] = {
            "pages": cleaned_page_list,
            "first_athlete": data.get("first_athlete") if isinstance(data, dict) else None,
            "last_athlete": data.get("last_athlete") if isinstance(data, dict) else None,
            "source_pdf": os.path.basename(pdf_path)
        }
    return cleaned_sport_map

if __name__ == "__main__":
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    SPORT_MAP_FILE = os.path.join(RESOURCES_DIR, "sport_map.json")

    # Dynamically find all PDF files in the resources directory to process
    INPUT_PDFS = [f for f in os.listdir(RESOURCES_DIR) if f.lower().endswith('.pdf')]
    print(f"Discovered {len(INPUT_PDFS)} PDF(s) in resources: {', '.join(INPUT_PDFS)}")

    combined_sport_map = {}
    for pdf_name in INPUT_PDFS:
        input_pdf_path = os.path.join(RESOURCES_DIR, pdf_name)
        if not os.path.exists(input_pdf_path):
            print(f"Warning: Source PDF not found at {input_pdf_path}. Skipping.")
            continue
            
        print(f"Generating sport mapping for: {input_pdf_path}")
        sport_map_segment = get_sport_mapping(input_pdf_path, PROJECT)
        combined_sport_map.update(sport_map_segment)

    if combined_sport_map:
        with open(SPORT_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(combined_sport_map, f, indent=4)
        print(f"Combined sport mapping saved to {SPORT_MAP_FILE}")