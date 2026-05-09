import os

def get_head_html(title: str) -> str:
    return f"""
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <link rel="icon" type="image/png" href="/img/favicon/favicon.png">
        <link rel="icon" type="image/x-icon" href="/img/favicon/favicon.ico">
        <link href="/static/css/output.css" rel="stylesheet">
    </head>
    """

def get_hero_section() -> str:
    return """
    <div class="inline-block px-4 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold uppercase tracking-widest mb-6">
        Hackathon Project
    </div>
    <h1 class="text-4xl font-black text-slate-900 mb-4">Hometown Heroes</h1>
    <p class="text-slate-600 text-lg mb-8 leading-relaxed">
        Exploring the geographic and climatic foundations of Team USA excellence. 
        Powered by <strong>Gemini 2.5 Pro</strong> and <strong>Google Cloud</strong>.
    </p>
    """

def get_stats_grid() -> str:
    return """
    <div class="mb-8">
        <a href="/hubs" class="bg-slate-50 p-4 rounded-xl border border-slate-100 block hover:bg-slate-100 transition">
            <span class="block text-2xl mb-1">📍</span>
            <span class="text-xs font-bold text-slate-500 uppercase">Regional Hubs</span>
        </a>
    </div>
    """

def get_action_links() -> str:
    return """
    <div class="flex flex-col space-y-3">
        <a href="/hubs" class="bg-blue-600 text-white px-8 py-3 rounded-xl font-bold hover:bg-blue-700 transition">
            Explore Regional Hubs
        </a>
        <a href="/docs" class="text-slate-600 text-sm font-bold hover:text-slate-900 transition">
            View API Documentation
        </a>
        <a href="/health" class="text-slate-400 text-sm hover:text-slate-600">
            System Health Check
        </a>
    </div>
    """

def get_footer_html() -> str:
    return """
    <div class="mt-12 pt-8 border-t border-slate-100">
        <div class="flex justify-center items-center space-x-4 opacity-50 grayscale">
            <img src="https://www.gstatic.com/images/branding/googlelogo/svg/google_logo_dark_clr_74x24px.svg" alt="Google Cloud" class="h-4">
        </div>
        <p class="mt-4 text-xs text-slate-400 max-w-sm mx-auto">
            Respecting NIL protections. Focusing on aggregate community insights. 
            Terminology consistent with Olympic Games Paris 2024 and LA28 Games.
        </p>
    </div>
    """

def render_landing_page() -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    {get_head_html("Hometown Heroes")}
    <body class="bg-slate-50 min-h-screen flex items-center justify-center">
        <div class="max-w-2xl bg-white p-12 rounded-3xl shadow-xl text-center">
            {get_hero_section()}
            {get_stats_grid()}
            {get_action_links()}
            {get_footer_html()}
        </div>
    </body>
    </html>
    """


def render_hub_detail_page(hometown_id: str, stats: list, narrative: str = None, pretty_name: str = None, api_key: str = None) -> str:
    # Format the hometown ID for display (e.g., boulder-co -> Boulder Co)
    display_name = pretty_name if pretty_name else hometown_id.replace('-', ' ').title()
    region = stats[0].get("region", "Global") if stats else "Unknown"
    
    # Script to fetch narrative asynchronously if not provided initially
    async_narrative_script = ""
    if not narrative:
        async_narrative_script = f"""
        <script>
            fetch('/api/v1/hubs/{hometown_id}', {{
                headers: {{ 'Authorization': 'Bearer {api_key}' }}
            }})
                .then(response => response.json())
                .then(data => {{
                    const el = document.getElementById('narrative-text');
                    if (data.narrative) el.innerText = `"${{data.narrative}}"`;
                }})
                .catch(err => console.error('Narrative fetch failed:', err));
        </script>
        """

    sport_items = ""
    bucket = f"{os.getenv('GOOGLE_CLOUD_PROJECT', '')}-hub-images"
    for item in stats:
        sport_id = item['sport_name'].lower().replace(" ", "_").replace("/", "_")
        icon_url = f"https://storage.googleapis.com/{bucket}/sports/{sport_id}.webp"
        sport_items += f"""
        <div class="bg-slate-100 p-8 rounded-3xl border border-slate-200 flex justify-between items-center shadow-sm">
            <div class="flex items-center">
                <div class="w-12 h-12 rounded-full bg-white border border-slate-200 overflow-hidden flex items-center justify-center p-1.5 shadow-sm flex-shrink-0">
                    <img src="{icon_url}" class="w-full h-full object-contain" onerror="this.parentElement.style.display='none'">
                </div>
                <div class="pl-6">
                    <span class="block text-base font-bold text-slate-500 uppercase tracking-wider mb-1">Sport</span>
                    <span class="text-3xl font-black text-slate-900">{item['sport_name']}</span>
                </div>
            </div>
            <div class="text-right">
                <span class="block text-base font-bold text-slate-500 uppercase tracking-wider mb-1">Athletes</span>
                <div class="flex justify-end">
                    <span class="flex items-center justify-center w-12 h-12 bg-blue-600 text-white rounded-full text-xl font-bold shadow-sm">
                        {item['athlete_count']}
                    </span>
                </div>
            </div>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    {get_head_html(f"{display_name} | Hometown Heroes")}
    <body class="bg-slate-50 min-h-screen py-12 px-4">
        <div class="max-w-4xl mx-auto bg-white p-12 rounded-3xl shadow-xl">
            <div class="mb-8">
                <a href="/hubs" class="text-blue-600 hover:text-blue-800 font-bold text-sm uppercase tracking-widest flex items-center">
                    <span class="mr-2">&larr;</span> Back to Map
                </a>
            </div>

            <h1 class="text-5xl font-black text-slate-900 mb-2">{display_name}</h1>
            <div class="inline-block px-4 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold uppercase tracking-widest mb-8">
                {region} Region
            </div>

            <div class="bg-blue-50 p-8 rounded-3xl border border-blue-100 mb-10">
                <h2 class="text-xl font-bold text-blue-900 mb-4 flex items-center">
                    <span class="mr-2">✨</span> Regional Narrative
                </h2>
                <p id="narrative-text" class="text-blue-900 leading-relaxed opacity-80">
                    {f'"{narrative}"' if narrative else "Gathering community insights and generating regional narrative..."}
                </p>
            </div>

            <h2 class="text-2xl font-black text-slate-900 mb-6">Sport Representation</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {sport_items}
            </div>

            {get_footer_html()}
        </div>
        {async_narrative_script}
    </body>
    </html>
    """