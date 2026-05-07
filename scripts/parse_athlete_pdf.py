import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import List, Dict, Set
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_sport_mapping(pdf_path: str, project_id: str) -> Dict[str, List[int]]:
    """
    Uses Gemini to identify which pages contain which sports.
    Returns a mapping of sport names to 1-based page numbers.
    """
    vertexai.init(project=project_id)
    model = GenerativeModel("gemini-2.5-flash-lite")
    
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    prompt = (
        "Analyze this Team USA athlete directory. Create a JSON mapping where keys are official sport names "
        "and values are lists of the page numbers (1-based) where that sport's athletes are listed. "
        "Note that a sport can span multiple pages and a page can have multiple sports."
    )
    
    response = model.generate_content([prompt, pdf_part], generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

def parse_athlete_pdf(pdf_path: str, output_json_path: str, project_id: str, sport_name: str, location: str = "us-central1") -> List[Dict]:
    """
    Uses Gemini 2.5 Flash Lite to parse a PDF for a specific sport into a structured JSON format.
    Ensures compliance with strict terminology and data formatting rules.
    """
    vertexai.init(project=project_id, location=location)
    # Use gemini-2.5-flash-lite for efficient parsing of structured data from PDFs
    model = GenerativeModel("gemini-2.5-flash-lite")

    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found.")
        return

    # Load the PDF file as bytes
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    # System instructions to enforce hackathon rules during extraction
    instructions = (
        f"Extract athlete information for the sport '{sport_name}' ONLY from the provided PDF. "
        "Ignore athletes from other sports. Format as a JSON list of objects.\n\n"
        "STRICT RULES:\n"
        "1. Terminology: Use 'Olympic Games [City] [Year]' or 'Olympic Winter Games [City] [Year]'.\n"
        "2. No 'PAST': Never use 'former' or 'past' Olympian. They are always Olympians.\n"
        "3. LA28: Use 'LA28 Games'.\n"
        "4. Keys: 'name', 'sport', 'hometown', 'participation_years'.\n"
        "5. If data is missing, use null."
    )

    prompt = f"Convert the athletes listed under the sport '{sport_name}' into a structured JSON list."

    # Create parts for the multimodal request
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    
    print(f"Analyzing PDF: {pdf_path}...")
    
    try:
        response = model.generate_content(
            [instructions, prompt, pdf_part],
            generation_config={"response_mime_type": "application/json"}
        )
        
        # The 'response_mime_type' configuration ensures Gemini returns valid JSON
        athlete_data = json.loads(response.text)
        
        # Save to file
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(athlete_data, f, indent=4)
            
        print(f"Successfully parsed {len(athlete_data)} records into {output_json_path}")
        return athlete_data
    except Exception as e:
        print(f"An error occurred during parsing: {e}")
        return []

if __name__ == "__main__":
    # Configuration
    PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
    
    if not PROJECT:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")

    # Calculate absolute paths relative to this script's directory
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    PAGES_DIR = os.path.join(RESOURCES_DIR, "pages")
    OUTPUT_DIR = os.path.join(RESOURCES_DIR, "output")
    INPUT_PDF = os.path.join(RESOURCES_DIR, "AllTimeHistory.pdf")

    # Ensure directories exist
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("""
    Script initialized. To run:
    1. Set GOOGLE_CLOUD_PROJECT environment variable.
    2. Ensure you have 'google-cloud-aiplatform' and 'pypdf' installed.
    3. Update the INPUT_PDF path in the script if necessary.
    """)

    if not os.path.exists(INPUT_PDF):
        print(f"Error: Source PDF not found at {INPUT_PDF}")
    else:
        print(f"Analyzing sport mapping for: {INPUT_PDF}")
        sport_map = get_sport_mapping(INPUT_PDF, PROJECT)
        
        reader = PdfReader(INPUT_PDF)
        seen_athletes: Set[tuple] = set()
        
        for idx, (sport, pages) in enumerate(sport_map.items(), 1):
            # Sanitize filename by replacing slashes and spaces
            sport_filename = sport.lower().replace(" ", "_").replace("/", "_")
            page_pdf_path = os.path.join(PAGES_DIR, f"{sport_filename}.pdf")
            page_json_path = os.path.join(OUTPUT_DIR, f"{idx}_{sport_filename}.json")

            # Check if this sport has already been processed to pick up where we left off
            if os.path.exists(page_json_path):
                print(f"Skipping {sport} (already exists at {page_json_path}). Loading athletes for deduplication...")
                try:
                    with open(page_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        for athlete in data:
                            seen_athletes.add((athlete.get('name'), athlete.get('sport')))
                except Exception as e:
                    print(f"Warning: Could not read existing file {page_json_path}, will re-process: {e}")
                else:
                    continue

            print(f"\n--- Processing {sport} (Pages {pages}) ---")
            
            # Create a combined PDF for the sport
            writer = PdfWriter()
            for p_num in pages:
                if 1 <= p_num <= len(reader.pages):
                    writer.add_page(reader.pages[p_num - 1])
            
            with open(page_pdf_path, "wb") as f:
                writer.write(f)
            
            # Parse the sport PDF with a specific filter for that sport
            data = parse_athlete_pdf(page_pdf_path, page_json_path, PROJECT, sport)
            
            if data:
                # Filter duplicates across the entire run based on name and sport
                unique_data = []
                for athlete in data:
                    key = (athlete.get('name'), athlete.get('sport'))
                    if key not in seen_athletes:
                        seen_athletes.add(key)
                        unique_data.append(athlete)
                
                # Save deduplicated data back to the file
                with open(page_json_path, "w", encoding="utf-8") as f:
                    json.dump(unique_data, f, indent=4)