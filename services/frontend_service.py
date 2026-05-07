def get_head_html(title: str) -> str:
    return f"""
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <script src="https://cdn.tailwindcss.com"></script>
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
    <div class="grid grid-cols-2 gap-4 mb-8">
        <div class="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <span class="block text-2xl mb-1">🏅</span>
            <span class="text-xs font-bold text-slate-500 uppercase">Olympic Games</span>
        </div>
        <div class="bg-slate-50 p-4 rounded-xl border border-slate-100">
            <span class="block text-2xl mb-1">🦾</span>
            <span class="text-xs font-bold text-slate-500 uppercase">Paralympic Games</span>
        </div>
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
        <p class="mt-4 text-[10px] text-slate-400 max-w-sm mx-auto">
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

def render_hubs_page(hubs: list, google_maps_api_key: str) -> str:
    # Prepare hub data for JavaScript
    hubs_js_array = []
    for hub in hubs:
        hubs_js_array.append(f"""
            {{
                id: '{hub['id']}',
                city: '{hub['city']}',
                lat: {hub['lat']},
                lng: {hub['lng']},
                description: `{hub['description']}`
            }}
        """)
    hubs_js = ",\n".join(hubs_js_array)

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    {get_head_html("Regional Hubs | Hometown Heroes")}
    <body class="bg-slate-50 min-h-screen flex flex-col items-center py-8 px-4">
        <div class="max-w-6xl w-full bg-white p-6 md:p-8 rounded-3xl shadow-xl">
            <div class="mb-6">
                <a href="/" class="text-blue-600 hover:underline text-xs font-bold uppercase tracking-widest">&larr; Back to Home</a>
            </div>
            <h1 class="text-4xl font-black text-slate-900 mb-6">Regional Success Hubs</h1>
            <p class="text-slate-600 text-lg mb-8 leading-relaxed">
                Explore the geographic centers that foster Team USA excellence. Click on a city to see its aggregate statistics and narrative.
            </p>
            <div id="map" style="height: 600px; width: 100%; border-radius: 1rem; margin-bottom: 2rem;"></div>
            <script>
                let map;
                const hubs = [
                    {hubs_js}
                ];

                async function initMap() {{
                    const {{ Map }} = await google.maps.importLibrary("maps");
                    const {{ AdvancedMarkerElement }} = await google.maps.importLibrary("marker");

                    map = new Map(document.getElementById("map"), {{
                        center: {{ lat: 39.8283, lng: -98.5795 }}, // Center of the US
                        zoom: 4,
                        mapId: "HOMETOWN_HEROES_MAP", // You can create a custom map style in Google Cloud Console
                        disableDefaultUI: true,
                        zoomControl: true,
                    }});

                    hubs.forEach(hub => {{
                        const marker = new AdvancedMarkerElement({{
                            map: map,
                            position: {{ lat: hub.lat, lng: hub.lng }},
                            title: hub.city,
                        }});

                        marker.addListener("click", () => {{
                            // Navigate to the hub's detail page
                            window.location.href = `/api/v1/hubs/${{hub.id}}`;
                        }});
                    }});
                }}

                initMap();
            </script>
            <script async src="https://maps.googleapis.com/maps/api/js?key={google_maps_api_key}&callback=initMap&v=beta&libraries=marker"></script>
            <div class="mt-8">
                {get_footer_html()}
            </div>
        </div>
    </body>
    </html>
    """