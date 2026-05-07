import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import List, Dict, Set
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_sport_mapping(pdf_path: str, project_id: str, location: str = "us-central1") -> Dict[str, List[int]]:
    """
    Uses Gemini to identify which pages contain which sports.
    Returns a mapping of sport names to 1-based page numbers.
    """
    vertexai.init(project=project_id, location=location)
    model = GenerativeModel("gemini-2.5-flash-lite")
    
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    prompt = (
        "Thoroughly analyze this Team USA athlete directory to create a comprehensive sport-to-page index. "
        "Return a JSON mapping where keys are official sport names and values are arrays of ALL 1-based page numbers "
        "where that sport's athletes are listed.\n\n"
        "CRITICAL BOUNDARY RULES:\n"
        "1. Identify the exact page where a sport starts (look for large section headers) and the exact page where it ends.\n"
        "2. Include EVERY page in the range. For example, if 'Soccer' begins on page 53 and continues through 57, "
        "the list must be [53, 54, 55, 56, 57]. Do not omit the start or end pages."
    )
    
    response = model.generate_content([prompt, pdf_part], generation_config={"response_mime_type": "application/json"})
    return json.loads(response.text)

def parse_athlete_pdf(pdf_path: str, project_id: str, sport_name: str, location: str = "us-central1", save_to_json: bool = False, output_json_path: str = None) -> List[Dict]:
    """
    Uses Gemini 2.5 Flash Lite to parse a PDF for a specific sport into a structured JSON format.
    Ensures compliance with strict terminology and data formatting rules.
    """
    vertexai.init(project=project_id, location=location)
    # Use gemini-2.5-flash-lite for efficient parsing of structured data from PDFs
    model = GenerativeModel("gemini-2.5-flash")

    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found.")
        return []

    # Load the PDF file as bytes
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    # System instructions to enforce hackathon rules during extraction
    instructions = (
        f"Thoroughly extract ALL athlete information for the sport '{sport_name}' from the provided PDF. "
        "The athletes are listed alphabetically. Continue extracting names until the end of the document or a clear new section (which should not occur if the PDF is correctly pre-filtered for this sport). "
        "Ignore athletes from other sports if any are present (though they should not be). Format the output as a JSON list of objects.\n\n"
        "STRICT RULES:\n"
        "1. Keys: 'name' (string), 'sport' (string), 'hometown' (string or null), 'participation_years' (list of integers, e.g., [2004, 2008]).\n"
        "2. If data is missing, use null."
    )

    prompt = f"Convert the athletes listed under the sport '{sport_name}' into a structured JSON list."

    # Create parts for the multimodal request
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    print(f"PDF part created for {sport_name}. Size: {len(pdf_data)} bytes.")
    
    print(f"Analyzing PDF: {pdf_path}...")
    
    if not save_to_json:
        return []

    try:
        response = model.generate_content(
            [instructions, prompt, pdf_part],
            generation_config={"response_mime_type": "application/json"}
        )
        
        athlete_data = json.loads(response.text)
        if athlete_data:
            print(f"First athlete in {sport_name}: {athlete_data[0].get('name', 'N/A')}")
            print(f"Last athlete in {sport_name}: {athlete_data[-1].get('name', 'N/A')}")
        else:
            print(f"No athletes found for {sport_name}.")

        if output_json_path:
            with open(output_json_path, "w", encoding="utf-8") as f:
                json.dump(athlete_data, f, indent=4)
            print(f"Successfully parsed {len(athlete_data)} records and saved to {output_json_path}")

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
            
            if not os.path.exists(page_pdf_path):
                # Create a combined PDF for the sport
                writer = PdfWriter()
                for p_num in pages:
                    if 1 <= p_num <= len(reader.pages):
                        writer.add_page(reader.pages[p_num - 1])
                
                with open(page_pdf_path, "wb") as f:
                    writer.write(f)
                print(f"Created sport-specific PDF: {page_pdf_path}")
            else:
                print(f"Using existing PDF for {sport}: {page_pdf_path}")
            
            # Parse the sport PDF. We set save_to_json=True to enable the model call.
            # We pass output_json_path=None here to avoid double-writing, 
            # as we handle the deduplicated save below.
            data = parse_athlete_pdf(
                page_pdf_path, PROJECT, sport, save_to_json=True, output_json_path=None
            )
            
            if data:
                # Filter duplicates across the entire run based on name and sport
                unique_data = []
                for athlete in data:
                    key = (athlete.get('name'), athlete.get('sport'))
                    if key not in seen_athletes:
                        seen_athletes.add(key)
                        unique_data.append(athlete)
                
                # The JSON is already saved by parse_athlete_pdf if save_to_json was True
                # If further deduplication is needed, it should be applied to the file after initial save
                # For now, we assume the initial save is sufficient or deduplication happens elsewhere.
                # If the intent is to save the *deduplicated* data, the saving logic needs to be here.
                # Re-saving the deduplicated data:
                if unique_data:
                    with open(page_json_path, "w", encoding="utf-8") as f:
                        json.dump(unique_data, f, indent=4)
                    print(f"Successfully deduplicated and saved {len(unique_data)} unique records to {page_json_path}")
                else:
                    print(f"No unique data found for {sport} after deduplication.")