import os
import json
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from typing import List, Dict, Set
from pypdf import PdfReader
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def parse_athlete_pdf(
    pdf_path: str, project_id: str, sport_name: str, location: str = "us-central1", 
    save_to_json: bool = False, output_json_path: str = None,
    expected_first: str = None, expected_last: str = None
) -> List[Dict]:
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
        "The athletes are arranged in columns positioned from left to right, and the names are listed in alphabetical order. Note that the list can continue onto the next page. "
        "Continue extracting names until the end of the document or a clear new section (which should not occur if the PDF is correctly pre-filtered for this sport). "
        "Ignore athletes from other sports if any are present (though they should not be). Format the output as a JSON list of objects.\n\n"
        "STRICT RULES:\n"
        "1. Keys: 'name' (string), 'sport' (string), 'hometown' (string or null), 'participation_years' (list of integers, e.g., [2004, 2008]).\n"
        "2. If data is missing, use null.\n"
        "3. Preserve the athlete's name EXACTLY as it appears in the PDF. Do not reformat, normalize, or change the casing (e.g., if 'SMITH, John', keep it as 'SMITH, John')."
    )

    prompt = f"Convert the athletes listed under the sport '{sport_name}' into a structured JSON list."

    # Create parts for the multimodal request
    pdf_part = Part.from_data(data=pdf_data, mime_type="application/pdf")
    print(f"PDF part created for {sport_name}. Size: {len(pdf_data)} bytes.")
    
    print(f"Analyzing PDF: {pdf_path}...")
    
    if not save_to_json:
        return []

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = model.generate_content(
                [instructions, prompt, pdf_part],
                generation_config={"response_mime_type": "application/json"}
            )
            
            athlete_data = json.loads(response.text)
            if athlete_data:
                actual_first = athlete_data[0].get('name', 'N/A')
                actual_last = athlete_data[-1].get('name', 'N/A')
                print(f"Attempt {attempt} - First athlete in {sport_name}: {actual_first}")
                print(f"Attempt {attempt} - Last athlete in {sport_name}: {actual_last}")

                # Verify extracted boundaries against the sport_map
                start_mismatch = expected_first and actual_first != expected_first
                end_mismatch = expected_last and actual_last != expected_last

                if start_mismatch or end_mismatch:
                    if start_mismatch:
                        print(f"WARNING: Start boundary mismatch. Expected: '{expected_first}', Got: '{actual_first}'")
                    if end_mismatch:
                        print(f"WARNING: End boundary mismatch. Expected: '{expected_last}', Got: '{actual_last}'")
                        # Refine instructions for the retry attempt to fix the boundary mismatch
                        instructions += (
                            f"\n\nNote for retry: Start from the current boundary ('{actual_last}') and continue from that point to the next athlete "
                            "(potentially checking the next column or if it's the last column, the next page) and continue until reaching the next sport title."
                        )
                    
                    if attempt < max_attempts:
                        print(f"Retrying extraction for {sport_name}...")
                        continue

            if output_json_path:
                with open(output_json_path, "w", encoding="utf-8") as f:
                    json.dump(athlete_data, f, indent=4)
                print(f"Successfully parsed {len(athlete_data)} records and saved to {output_json_path}")

            return athlete_data
        except Exception as e:
            print(f"An error occurred during parsing on attempt {attempt}: {e}")
            if attempt == max_attempts:
                return []
    
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
        SPORT_MAP_FILE = os.path.join(RESOURCES_DIR, "sport_map.json")
        if not os.path.exists(SPORT_MAP_FILE):
            print(f"Error: Sport mapping file not found at {SPORT_MAP_FILE}.")
            print("Please run 'generate_sport_map.py' first to create the sport mapping.")
            exit()
        
        with open(SPORT_MAP_FILE, "r", encoding="utf-8") as f:
            sport_map = json.load(f)
        
        # --- CONVERSION PHASE ---
        print("\n--- Starting PDF to JSON Conversion ---")
        seen_athletes: Set[tuple] = set()
        
        for idx, (sport, data) in enumerate(sport_map.items(), 1):
            pages = data.get("pages", [])
            # Sanitize filename by replacing slashes and spaces
            sport_filename = sport.lower().replace(" ", "_").replace("/", "_")
            page_pdf_path = os.path.join(PAGES_DIR, f"{sport_filename}.pdf")
            page_json_path = os.path.join(OUTPUT_DIR, f"{idx}_{sport_filename}.json")

            # Check if this sport has already been processed to pick up where we left off
            if os.path.exists(page_json_path):
                print(f"Skipping {sport} (already exists at {page_json_path}). Loading athletes for deduplication...")
                try:
                    with open(page_json_path, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        for athlete in existing_data:
                            seen_athletes.add((athlete.get('name'), athlete.get('sport')))
                except Exception as e:
                    print(f"Warning: Could not read existing file {page_json_path}, will re-process: {e}")
                else:
                    continue

            print(f"\n--- Converting {sport} ---")
            
            if not os.path.exists(page_pdf_path):
                print(f"Warning: PDF segment for {sport} not found. Skipping.")
                continue
            
            # Parse the sport PDF. We set save_to_json=True to enable the model call.
            # We pass output_json_path=None here to avoid double-writing, 
            # as we handle the deduplicated save below.
            extracted_athletes = parse_athlete_pdf(
                page_pdf_path, PROJECT, sport, save_to_json=True, output_json_path=None,
                expected_first=data.get("first_athlete"),
                expected_last=data.get("last_athlete")
            )
            
            if extracted_athletes:
                # Filter duplicates across the entire run based on name and sport
                unique_data = []
                for athlete in extracted_athletes:
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