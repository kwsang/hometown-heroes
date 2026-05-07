import os
import json
from pypdf import PdfReader, PdfWriter
from dotenv import load_dotenv
from typing import Dict

# Load environment variables from .env file
load_dotenv()

def split_pdf_by_sport(input_pdf_path: str, sport_map: Dict[str, Dict], pages_dir: str):
    """
    Splits the input PDF into sport-specific files based on the provided sport mapping.
    """
    reader = PdfReader(input_pdf_path)
    for sport, data in sport_map.items():
        pages = data.get("pages", [])
        sport_filename = sport.lower().replace(" ", "_").replace("/", "_")
        page_pdf_path = os.path.join(pages_dir, f"{sport_filename}.pdf")
        
        if not os.path.exists(page_pdf_path):
            writer = PdfWriter()
            for p_num in pages:
                if 1 <= p_num <= len(reader.pages):
                    writer.add_page(reader.pages[p_num - 1])
            
            with open(page_pdf_path, "wb") as f:
                writer.write(f)
            print(f"Created segment for {sport}: {page_pdf_path}")
        else:
            print(f"Segment exists for {sport}: {page_pdf_path}")

if __name__ == "__main__":
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")
    PAGES_DIR = os.path.join(RESOURCES_DIR, "pages")
    INPUT_PDF = os.path.join(RESOURCES_DIR, "AllTimeHistory.pdf")
    SPORT_MAP_FILE = os.path.join(RESOURCES_DIR, "sport_map.json")

    os.makedirs(PAGES_DIR, exist_ok=True)

    if not os.path.exists(INPUT_PDF):
        print(f"Error: Source PDF not found at {INPUT_PDF}")
    elif not os.path.exists(SPORT_MAP_FILE):
        print(f"Error: Sport mapping file not found at {SPORT_MAP_FILE}. Run generate_sport_map.py first.")
    else:
        print(f"Loading sport map from {SPORT_MAP_FILE}")
        with open(SPORT_MAP_FILE, "r", encoding="utf-8") as f:
            sport_map = json.load(f)

        # --- CHUNKING LOGIC ---
        # Large sports (like Track & Field) exceed Gemini's output token limit for JSON responses.
        # We split these into manageable segments (max 1 page per PDF segment).
        MAX_PAGES = 1
        chunked_map = {}

        for sport, data in sport_map.items():
            pages = data.get("pages", [])
            if len(pages) <= MAX_PAGES:
                chunked_map[sport] = data
            else:
                print(f"Sport {sport} spans {len(pages)} pages. Splitting into chunks of {MAX_PAGES}...")
                # Split page list into sub-lists of size MAX_PAGES
                chunks = [pages[i:i + MAX_PAGES] for i in range(0, len(pages), MAX_PAGES)]
                for i, chunk_pages in enumerate(chunks):
                    part_name = f"{sport} (Part {i+1})"
                    chunked_map[part_name] = {
                        "pages": chunk_pages,
                        # Boundary verification only works for the global start and global end
                        "first_athlete": data.get("first_athlete") if i == 0 else None,
                        "last_athlete": data.get("last_athlete") if i == len(chunks) - 1 else None
                    }

        # Update the sport_map file so downstream scripts (parser) use the chunks
        with open(SPORT_MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(chunked_map, f, indent=4)
        print(f"Updated {SPORT_MAP_FILE} with chunked sport entries.")
        
        print("\n--- Starting PDF Splitting ---")
        split_pdf_by_sport(INPUT_PDF, chunked_map, PAGES_DIR)
        print("\nSplitting complete. Please verify the files in resources/pages.")