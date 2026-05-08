from services import frontend_service, hub_drawer_service

def render_hubs_page(hubs: list, google_maps_api_key: str, api_key: str = None) -> str:
    """Renders the interactive Google Maps page with regional hubs and legend."""
    # Prepare hub data for JavaScript
    hubs_js_array = []
    for hub in hubs:
        hubs_js_array.append(f"""
            {{
                id: '{hub['id']}',
                city: '{hub['city']}',
                pretty_city_name: '{hub['pretty_city_name']}',
                athlete_count: {hub['total_athlete_count']},
                lat: {hub['lat']},
                lng: {hub['lng']},
                region: '{hub['region']}',
                description: `{hub['description']}`
            }}
        """)
    hubs_js = ",\n".join(hubs_js_array)

    # Define region colors for the legend (matching the JavaScript mapping)
    region_colors = {
        'Pacific': '#3b82f6',
        'Mountain': '#8b5cf6',
        'Midwest': '#10b981',
        'Northeast': '#ef4444',
        'South': '#f59e0b',
        'The Heartland': '#06b6d4',
        'The Desert Southwest': '#f97316',
        'Global': '#64748b'
    }

    legend_items = "".join([
        f"""
        <button 
            onclick="toggleRegion('{name}')" 
            data-region-btn="{name}"
            class="flex items-center space-x-2 px-3 py-2 rounded-xl transition-all duration-200 border border-transparent hover:bg-white hover:shadow-sm"
        >
            <span class="w-2.5 h-2.5 rounded-full" style="background-color: {color};"></span>
            <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{name}</span>
        </button>
        """ for name, color in region_colors.items()
    ])
    legend_html = f"""
    <div class="flex flex-wrap items-center justify-between gap-6 mb-8 bg-slate-50 p-4 rounded-2xl border border-slate-100">
        <div class="flex flex-wrap gap-x-4 gap-y-2">
            {legend_items}
        </div>
        <div class="flex flex-col space-y-2 min-w-[200px] border-l border-slate-200 pl-6 ml-auto">
            <label for="athlete-range" class="text-xs font-bold text-slate-500 uppercase tracking-widest flex justify-between">
                <span>Min Athletes</span>
                <span id="range-value" class="text-blue-600 font-black">4</span>
            </label>
            <input type="range" id="athlete-range" min="1" max="100" value="4" 
                   class="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                   oninput="updateAthleteFilter(this.value)">
        </div>
    </div>
    """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    {frontend_service.get_head_html("Regional Hubs | Hometown Heroes")}
    <body class="bg-slate-50 min-h-screen flex flex-col items-center py-8 px-4">
        <div class="max-w-[98vw] w-full bg-white p-6 md:p-8 rounded-3xl shadow-xl transition-all duration-500">
            <div class="mb-6">
                <a href="/" class="text-blue-600 hover:underline text-xs font-bold uppercase tracking-widest">&larr; Back to Home</a>
            </div>
            <h1 class="text-4xl font-black text-slate-900 mb-6">Regional Success Hubs</h1>
            <p class="text-slate-600 text-lg mb-8 leading-relaxed">
                Explore the geographic centers that foster Team USA excellence. Click on a city to see its aggregate statistics and narrative.
            </p>
            {legend_html}
            
            <div class="flex h-[85vh] w-full rounded-3xl overflow-hidden border border-slate-100 shadow-sm mb-8">
                <div id="map" class="flex-grow h-full"></div>
                {hub_drawer_service.get_drawer_html()}
            </div>

            <script>
                let map;
                const markers = [];
                const selectedRegions = new Set();
                let minAthletes = 4;
                const hubs = [
                    {hubs_js}
                ];

                async function initMap() {{
                    const {{ Map }} = await google.maps.importLibrary("maps");
                    const {{ AdvancedMarkerElement, PinElement }} = await google.maps.importLibrary("marker");

                    const regionColors = {{
                        'Pacific': '#3b82f6',
                        'Mountain': '#8b5cf6',
                        'Midwest': '#10b981',
                        'Northeast': '#ef4444',
                        'South': '#f59e0b',
                        'The Heartland': '#06b6d4',
                        'The Desert Southwest': '#f97316',
                        'Global': '#64748b'
                    }};

                    map = new Map(document.getElementById("map"), {{
                        center: {{ lat: 39.8283, lng: -98.5795 }}, // Center of the US
                        zoom: 4,
                        mapId: "HOMETOWN_HEROES_MAP", // You can create a custom map style in Google Cloud Console
                        disableDefaultUI: true,
                        zoomControl: true,
                        gestureHandling: 'greedy',
                    }});

                    hubs.forEach(hub => {{
                        const pin = new PinElement({{
                            background: regionColors[hub.region] || regionColors['Global'],
                            borderColor: '#ffffff',
                            glyphColor: '#ffffff',
                        }});

                        const marker = new AdvancedMarkerElement({{
                            map: map,
                            position: {{ lat: hub.lat, lng: hub.lng }},
                            title: hub.city,
                            content: pin.element,
                        }});
                        
                        marker.region = hub.region;
                        marker.athleteCount = hub.athlete_count;
                        markers.push(marker);

                        marker.addListener("click", () => {{
                            openDrawer(hub.id, hub.pretty_city_name);
                        }});
                    }});

                    // Setup range slider max dynamically based on data
                    const maxAthletes = Math.max(...hubs.map(h => h.athlete_count), 10);
                    const rangeInput = document.getElementById('athlete-range');
                    if (rangeInput) rangeInput.max = maxAthletes;

                    // Apply initial filters
                    updateFilters();
                }}

                window.toggleRegion = (region) => {{
                    if (selectedRegions.has(region)) {{
                        selectedRegions.delete(region);
                    }} else {{
                        selectedRegions.add(region);
                    }}
                    updateFilters();
                }};

                window.updateAthleteFilter = (val) => {{
                    minAthletes = parseInt(val);
                    document.getElementById('range-value').innerText = val;
                    updateFilters();
                }};

                function updateFilters() {{
                    const btns = document.querySelectorAll('[data-region-btn]');
                    const isFilteringRegions = selectedRegions.size > 0;

                    btns.forEach(btn => {{
                        const region = btn.getAttribute('data-region-btn');
                        const isActive = selectedRegions.has(region);

                        btn.classList.toggle('bg-white', isActive);
                        btn.classList.toggle('shadow-sm', isActive);
                        btn.classList.toggle('border-slate-200', isActive);
                        btn.style.opacity = (!isFilteringRegions || isActive) ? "1" : "0.4";
                        btn.style.filter = (!isFilteringRegions || isActive) ? "none" : "grayscale(100%)";
                    }});

                    markers.forEach(m => {{
                        const matchesRegion = !isFilteringRegions || selectedRegions.has(m.region);
                        const matchesCount = m.athleteCount >= minAthletes;
                        m.map = (matchesRegion && matchesCount) ? map : null;
                    }});
                }}
                {hub_drawer_service.get_drawer_js(api_key)}

                initMap();
            </script>
            <script async src="https://maps.googleapis.com/maps/api/js?key={google_maps_api_key}&callback=initMap&v=beta&libraries=marker"></script>
            <div class="mt-8 text-center">
                <a href="/" class="text-blue-600 hover:underline text-sm font-bold uppercase tracking-widest">
                    &larr; Back to Home
                </a>
            </div>
        </div>
    </body>
    </html>
    """