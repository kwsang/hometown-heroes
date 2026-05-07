from services import frontend_service, hub_drawer_service

def render_hubs_page(hubs: list, google_maps_api_key: str) -> str:
    """Renders the interactive Google Maps page with regional hubs and legend."""
    # Prepare hub data for JavaScript
    hubs_js_array = []
    for hub in hubs:
        hubs_js_array.append(f"""
            {{
                id: '{hub['id']}',
                city: '{hub['city']}',
                pretty_city_name: '{hub['pretty_city_name']}',
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
        <div class="flex items-center space-x-2">
            <span class="w-3 h-3 rounded-full" style="background-color: {color};"></span>
            <span class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{name}</span>
        </div>
        """ for name, color in region_colors.items()
    ])
    legend_html = f'<div class="flex flex-wrap gap-x-6 gap-y-3 mb-8 bg-slate-50 p-6 rounded-2xl border border-slate-100">{legend_items}</div>'

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    {frontend_service.get_head_html("Regional Hubs | Hometown Heroes")}
    <body class="bg-slate-50 min-h-screen flex flex-col items-center py-8 px-4 overflow-x-hidden">
        {hub_drawer_service.get_drawer_html()}

        <div class="max-w-6xl w-full bg-white p-6 md:p-8 rounded-3xl shadow-xl">
            <div class="mb-6">
                <a href="/" class="text-blue-600 hover:underline text-xs font-bold uppercase tracking-widest">&larr; Back to Home</a>
            </div>
            <h1 class="text-4xl font-black text-slate-900 mb-6">Regional Success Hubs</h1>
            <p class="text-slate-600 text-lg mb-8 leading-relaxed">
                Explore the geographic centers that foster Team USA excellence. Click on a city to see its aggregate statistics and narrative.
            </p>
            {legend_html}
            <div id="map" style="height: 600px; width: 100%; border-radius: 1rem; margin-bottom: 2rem;"></div>
            <script>
                let map;
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

                        marker.addListener("click", () => {{
                            openDrawer(hub.id, hub.pretty_city_name);
                        }});
                    }});
                }}
                {hub_drawer_service.get_drawer_js()}

                initMap();
            </script>
            <script async src="https://maps.googleapis.com/maps/api/js?key={google_maps_api_key}&callback=initMap&v=beta&libraries=marker"></script>
            <div class="mt-8">
                {frontend_service.get_footer_html()}
            </div>
        </div>
    </body>
    </html>
    """