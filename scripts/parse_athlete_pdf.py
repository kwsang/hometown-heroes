import os
import json
import re
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
    model = GenerativeModel("gemini-2.5-flash-lite")

    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found.")
        return []

    # Load the PDF file as bytes
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()

    # System instructions to enforce hackathon rules during extraction
    instructions = (
        f"Thoroughly extract ALL athlete information for the sport '{sport_name}' from the provided PDF. "
        "The athletes are arranged in columns positioned from left to right, and the names are listed in alphabetical order. "
        "Note that the list often continues onto the next column or subsequent page. "
    )
    
    if expected_first:
        instructions += f" The first athlete in your output MUST be '{expected_first}'."
    if expected_last:
        instructions += f" The last athlete in your output MUST be '{expected_last}'."
        
    instructions += (
        " Continue extracting names until you find a clear header indicating a new sport (typically large BLUE or RED text). "
         "Crucially, participation years often wrap to the next line. Ensure you collect ALL years for an athlete, even if the next athlete's name starts on the line immediately following the wrapped years. "
        "It is IMPERATIVE that you complete the extraction. To save space, format the output as a JSON list of lists where each inner list represents an athlete: [\"Name\", \"Hometown\", [Year1, Year2]]. "
        "Do NOT include the sport name in the inner list as it is redundant. "
        "Ensure the final output is a perfectly valid and complete JSON array. If you think you've reached the end of a section, check at least 5 more entries or the top of the next page to ensure no column transitions were missed. "
        "Ignore athletes from other sports. Do not include trailing commas or markdown formatting.\n\n"
        "STRICT RULES:\n"
        "1. Format: [[\"NAME, First\", \"City, State\", [2004, 2008]], ...]\n"
        "2. If hometown is missing, use null.\n"
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
            print(f"\n--- Gemini Request Context (Attempt {attempt}) ---")
            print(f"Instructions Snippet: {instructions[:200]}...")

            response = model.generate_content(
                [instructions, prompt, pdf_part],
                generation_config={
                    "response_mime_type": "application/json",
                    "max_output_tokens": 8192,
                    "temperature": 0.1,
                }
            )
            
            raw_text = response.text.strip()
            
            print(f"--- Raw Gemini Response (Length: {len(raw_text)}) ---")
            print(raw_text)
            print("--- End of Raw Response ---\n")

            # Clean up potential markdown formatting
            if raw_text.startswith("```"):
                raw_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', raw_text, flags=re.MULTILINE).strip()
            
            # 1. Fix double/multiple commas: [1, , 2] or [ {...}, , {...} ]
            raw_text = re.sub(r',(?:\s*,)+', ',', raw_text)
            
            # 2. Fix trailing commas: [1, 2, ] -> [1, 2]
            raw_text = re.sub(r',+\s*([\]}])', r'\1', raw_text)

            compact_data = json.loads(raw_text)
            
            # Transform compact array-of-arrays back to the expected list of dictionaries
            athlete_data = []
            for item in compact_data:
                athlete_data.append({
                    "name": item[0],
                    "sport": sport_name,
                    "hometown": item[1],
                    "participation_years": item[2]
                })

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
                    
                    # Refine instructions for the retry attempt to help Gemini recover
                    instructions += (
                        f"\n\nNote for retry: Your previous attempt stopped or failed near '{actual_last}'. "
                        "Please start from that point and ensure you check subsequent columns or pages for remaining athletes "
                        f"belonging to '{sport_name}' before finishing."
                    )

                    if attempt < max_attempts:
                        print(f"Retrying extraction for {sport_name}...")
                        continue

            if output_json_path:
                with open(output_json_path, "w", encoding="utf-8") as f:
                    json.dump(athlete_data, f, indent=4)
                print(f"Successfully parsed {len(athlete_data)} records and saved to {output_json_path}")

            return athlete_data
        except json.JSONDecodeError as jde:
            # Check if the error is likely due to truncation (end of string reached prematurely)
            if jde.pos >= len(raw_text) - 5:
                print(f"CRITICAL: JSON response for {sport_name} appears to be TRUNCATED by the model's token limit.")
                print(f"Total characters received: {len(raw_text)}. Track & Field may be too large for a single request.")
            
            print(f"JSON Decode Error for {sport_name} on attempt {attempt}: {jde}")
            # Print context around the error for debugging
            start_snippet = max(0, jde.pos - 40)
            end_snippet = min(len(raw_text), jde.pos + 40)
            print(f"Context: ...{raw_text[start_snippet:end_snippet]}...")
            if attempt == max_attempts:
                return []
        except Exception as e:
            print(f"Unexpected error during parsing on attempt {attempt}: {e}")
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
        
        # 1. Group entries by base sport name to handle multi-part consolidation
        grouped_sports = {}
        for sport_key, data in sport_map.items():
            # Strip " (Part X)" to get the official sport name for Gemini and consolidation
            base_name = re.sub(r'\s\(Part \d+\)$', '', sport_key)
            if base_name not in grouped_sports:
                grouped_sports[base_name] = []
            grouped_sports[base_name].append((sport_key, data))

        for base_sport, parts in grouped_sports.items():
            # Sanitize base filename for consolidated output
            base_filename = base_sport.lower().replace(" ", "_").replace("/", "_")
            final_json_path = os.path.join(OUTPUT_DIR, f"{base_filename}.json")

            # Check if JSON already exists in either output directories
            already_exists = False
            for check_dir in [OUTPUT_DIR]:
                if os.path.exists(os.path.join(check_dir, f"{base_filename}.json")):
                    already_exists = True
                    break
                # Check for legacy indexed files (e.g., "1_archery.json")
                if any(f.endswith(f"_{base_filename}.json") and f.split('_')[0].isdigit() for f in os.listdir(check_dir)):
                    already_exists = True
                    break

            if already_exists:
                print(f"Skipping {base_sport} (JSON already exists in output).")
                continue

            print(f"\n--- Processing Sport: {base_sport} ---")
            all_athletes_for_sport = []
            all_parts_available = True

            for sport_part_name, data in parts:
                # Sanitize part filename for PDF lookup and caching
                part_filename = sport_part_name.lower().replace(" ", "_").replace("/", "_")
                page_pdf_path = os.path.join(PAGES_DIR, f"{part_filename}.pdf")
                # Temporary file to cache parts for resume-ability
                part_cache_path = os.path.join(OUTPUT_DIR, f"cache_{part_filename}.json")

                if os.path.exists(part_cache_path):
                    print(f"  Loading cached data for {sport_part_name}...")
                    with open(part_cache_path, "r", encoding="utf-8") as f:
                        part_data = json.load(f)
                        all_athletes_for_sport.extend(part_data)
                else:
                    if not os.path.exists(page_pdf_path):
                        print(f"  Warning: PDF segment for {sport_part_name} not found.")
                        all_parts_available = False
                        break

                    print(f"  Converting {sport_part_name}...")
                    extracted = parse_athlete_pdf(
                        page_pdf_path, PROJECT, base_sport, save_to_json=True, 
                        output_json_path=part_cache_path,
                        expected_first=data.get("first_athlete"),
                        expected_last=data.get("last_athlete")
                    )
                    
                    if extracted:
                        all_athletes_for_sport.extend(extracted)
                    else:
                        print(f"  Error: Failed to extract data for {sport_part_name}.")
                        all_parts_available = False
                        break

            if all_parts_available and all_athletes_for_sport:
                with open(final_json_path, "w", encoding="utf-8") as f:
                    json.dump(all_athletes_for_sport, f, indent=4)
                print(f"Successfully consolidated {len(all_athletes_for_sport)} records into {final_json_path}")
                
                # Cleanup: Remove temporary cache files after successful consolidation
                for sport_part_name, _ in parts:
                    part_fn = sport_part_name.lower().replace(" ", "_").replace("/", "_")
                    cache_path = os.path.join(OUTPUT_DIR, f"cache_{part_fn}.json")
                    if os.path.exists(cache_path):
                        os.remove(cache_path)
            elif not all_parts_available:
                print(f"  Consolidation for {base_sport} aborted due to missing parts.")