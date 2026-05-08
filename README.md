# hometown-heroes
## The Hometown Success Engine

### 🌟 Inspiration
The inspiration for **Hometown Heroes** stems from a desire to celebrate the collective power of Team USA by connecting elite athletic performance to the American landscape. Rather than focusing solely on podium finishes, we wanted to visualize how local environments—geography, climate, and community—foster excellence across both Olympic and Paralympic disciplines. By identifying "Hubs" of talent, we aim to inspire the next generation of athletes by showing them that the path to the Games often starts in their own backyard.

### 🏗️ How We Built It
The project is powered by a robust ETL pipeline and a multi-tiered AI architecture:
1.  **Data Extraction:** We used **Gemini 2.5 Flash Lite** to perform multimodal parsing of official Team USA athlete PDFs. This allowed us to extract structured data from complex layouts without manual OCR.
2.  **Enrichment:** Athlete data was enriched with hometown geocoding via the **Google Maps API** and elevation data to analyze geographic trends.
3.  **Intelligence & Narratives:** We leveraged **Gemini 2.5 Pro** to generate compliant, inspiring narratives for each regional hub, correlating local terrain and climate with sport-specific success.
4.  **Asset Optimization:** Using **Imagen 3.0**, we generate custom hub imagery, which is then optimized into `.webp` format and served via **Google Cloud Storage** for lightning-fast frontend delivery.
5.  **Multi-Tiered Storage:** **Google BigQuery** acts as our analytical source of truth and narrative cache, while **Cloud Firestore** serves as a high-performance NoSQL serving layer for sub-second map and drawer responsiveness.

### 🧠 What We Learned
*   **Multimodal AI is a Game Changer:** Using Gemini to "read" PDFs directly saved dozens of hours of manual data entry and regular expression tuning.
*   **Structured Output Engineering:** We learned how to strictly enforce JSON schemas and boundary validation (first/last athlete checks) to ensure 100% data integrity when working with LLMs.
*   **Serving Layer Separation:** Moving real-time "reads" from BigQuery to **Cloud Firestore** transformed the user experience from "loading..." to "instant." 
*   **The Power of WebP:** Transitioning from PNG to optimized WebP reduced image payloads by over 80% without visible quality loss.
*   **Compliance-First Design:** Navigating the strict NIL (Name, Image, and Likeness) and branding restrictions taught us how to build meaningful data products while respecting athlete privacy and intellectual property.

### 🚧 Challenges Faced
*   **PDF Complexity:** Large sports like "Track & Field" exceeded token limits, requiring us to build a custom PDF segmenting tool to chunk data for the API.
*   **API Rate Limits:** Orchestrating thousands of calls to Gemini and Google Maps required implementing robust exponential backoff and staging table patterns in BigQuery to avoid streaming buffer conflicts.
*   **Terminology Strictness:** Ensuring the AI never used "past" or "former" for Olympians and correctly identified "Olympic Games [City] [Year]" required fine-tuning system instructions and post-processing validation.

### 🛠️ Tech Stack

**Languages & Frameworks:**
*   **Python:** The core of our ETL and backend services.
*   **FastAPI:** Powering the high-performance serving tier.
*   **Tailwind CSS & Vanilla JS:** For a lightweight, responsive interactive map dashboard.

**Google Cloud Platform Services:**
*   **Vertex AI:** Hosting Gemini 2.5 Pro/Flash and Imagen models.
*   **BigQuery:** Data warehousing and ML-driven enrichment.
*   **Cloud Firestore:** High-performance NoSQL serving layer.
*   **Cloud Storage:** Hosting optimized AI-generated assets.
*   **Cloud Run:** Deployment of the serving tier.

**APIs & AI Models:**
*   **Gemini 2.5 Pro:** Narrative generation and complex reasoning.
*   **Gemini 2.5 Flash & Flash Lite:** High-throughput PDF parsing and data cleaning.
*   **Imagen 3.0:** Hub image generation.
*   **Google Maps Platform:** Geocoding and Elevation APIs.

**Tools & Libraries:**
*   `pypdf` for programmatic PDF manipulation.
*   `pandas` for local data aggregation.
*   `google-cloud-aiplatform` and `google-cloud-bigquery` for GCP integration.

### 🔑 Prerequisites & Permissions
To successfully deploy and manage this project, ensure your Google Cloud user or service account has the following roles and permissions:
*   **Deployment:** `Cloud Run Admin`, `Cloud Build Editor`, and `Service Account User`.
*   **Data & AI:** `BigQuery Data Editor`, `BigQuery User`, `Vertex AI User`, `Cloud Datastore User` (for Firestore), and `Storage Object Admin`.
*   **Security:** `Secret Manager Secret Accessor` (if using Secret Manager for API keys).
*   **Observability:** To view and debug application logs, you must have the `logging.logEntries.list` permission (typically included in **Project Viewer** or **Logs Viewer** roles).

### 🛠️ Managing the Service Account
To find the exact email of the service account your app is using:
```bash
gcloud run services describe hometown-heroes --format="value(spec.template.spec.serviceAccountName)"
```

To grant permissions (e.g., BigQuery access) to that account:
```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" --role="roles/bigquery.dataViewer"
```

---
*This project was developed for the Team USA Hackathon, adhering to all athlete NIL protections and official terminology requirements.*
