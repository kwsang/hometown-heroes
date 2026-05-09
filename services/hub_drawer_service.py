import os
from services import ai_insights_service

def get_drawer_html() -> str:
    """Returns the HTML structure for the hub details side drawer."""
    return """
        <!-- Details Drawer -->
        <div id="drawer" class="w-0 transition-all duration-500 ease-in-out overflow-y-auto border-l border-transparent bg-white h-full relative">
            <div class="p-4 sticky top-0 bg-white/90 backdrop-blur-sm z-20 border-b border-slate-50">
                <button onclick="closeDrawer()" class="text-slate-400 hover:text-slate-900 font-bold uppercase text-xs tracking-widest flex items-center transition group">
                    <span class="mr-2 text-lg group-hover:-translate-x-1 transition-transform">✕</span> Close Details
                </button>
            </div>
            <div id="drawer-content" class="p-6 pt-1">
                <!-- Content injected via JS -->
            </div>
        </div>
    """

def get_drawer_js(project_id: str, api_key: str) -> str:
    """Returns the JavaScript logic for opening, closing, and populating the hub details drawer."""
    return rf"""
        let activeHighlightMarker = null;
        let currentlyHighlightedHubId = null;
        let lastFeaturedSport = null;
        let activeHubId = null;
        const narrativeCache = {}; // Client-side cache for session persistence

        function closeDrawer() {{
            const drawer = document.getElementById('drawer');
            drawer.classList.remove('w-full', 'md:w-[675px]', 'border-slate-100');
            drawer.classList.add('w-0', 'border-transparent');
            document.body.style.overflow = 'auto';

            // Reset all markers to their original state
            markers.forEach(m => {{
                if (m.content) {{
                    m.content.scale = 1.0;
                    m.content.borderColor = '#ffffff';
                }}
                m.zIndex = null;
            }});

            // Re-trigger random highlight after the requested 5s delay
            setTimeout(highlightRandomHub, 5000);
        }}

        function clearRandomHighlight() {{
            if (activeHighlightMarker) {{
                activeHighlightMarker.setMap(null);
                activeHighlightMarker = null;
            }}
            currentlyHighlightedHubId = null;
            markers.forEach(m => {{
                if (m.content && m.content.scale > 1.0) {{
                    m.content.scale = 1.0;
                    m.content.borderColor = '#ffffff';
                }}
            }});
        }}

        async function highlightRandomHub() {{
            if (document.getElementById('drawer').classList.contains('border-slate-100')) return;
            clearRandomHighlight();

            // 1. Find visible hubs
            const visibleMarkers = markers.filter(m => m.map !== null);
            if (visibleMarkers.length === 0) return;

            // 2. Identify top hubs by their strongest sport
            const candidateHubs = hubs.filter(h => visibleMarkers.some(m => m.id === h.id))
                .map(h => {{
                    const topSport = h.sports_data.reduce((prev, curr) => (prev.count > curr.count) ? prev : curr, {{count: 0, sport: 'Unknown'}});
                    return {{ ...h, topSport }};
                }})
                .sort((a, b) => b.topSport.count - a.topSport.count);

            // Favor sports different from the last featured one for variety
            const freshCandidates = candidateHubs.filter(h => h.topSport.sport !== lastFeaturedSport);
            const pool = freshCandidates.length > 0 ? freshCandidates.slice(0, 20) : candidateHubs.slice(0, 20);

            if (pool.length === 0) return;
            const target = pool[Math.floor(Math.random() * pool.length)];
            currentlyHighlightedHubId = target.id;
            lastFeaturedSport = target.topSport.sport;

            const marker = markers.find(m => m.id === target.id);

            if (marker && marker.content) {{
                // Enlarge
                marker.content.scale = 1.8;
                marker.content.borderColor = '#3b82f6';
                marker.zIndex = 500;

                // Create Floating Sport Bubble
                const sportId = target.topSport.sport.toLowerCase().replace(/ /g, "_").replace(/\//g, "_");
                const bucket = "{project_id}-hub-images";
                const iconUrl = `https://storage.googleapis.com/${{bucket}}/sports/${{sportId}}.webp`;

                const bubble = document.createElement('div');
                bubble.style.cursor = 'pointer';
                bubble.innerHTML = `
                    <div class="relative animate-bounce">
                        <div class="w-8 h-8 bg-white rounded-full border-2 border-blue-500 shadow-lg overflow-hidden flex items-center justify-center p-0.5">
                            <img src="${{iconUrl}}" class="w-full h-full object-contain" onerror="this.src='https://www.gstatic.com/images/branding/product/2x/googleg_32dp.png'">
                        </div>
                    </div>
                `;

                const {{ AdvancedMarkerElement }} = await google.maps.importLibrary("marker");
                activeHighlightMarker = new AdvancedMarkerElement({{
                    map: map,
                    position: {{ lat: target.lat + 0.5, lng: target.lng }}, // Offset slightly north
                    content: bubble,
                    zIndex: 600
                }});

                // Allow clicking the floating sport bubble to open the hub details
                activeHighlightMarker.addListener("gmp-click", () => {{
                    openDrawer(target.id, target.pretty_city_name);
                }});
            }}
        }}

        async function openDrawer(hubId, hubCity) {{
            const drawer = document.getElementById('drawer');
            const content = document.getElementById('drawer-content');
            
            clearRandomHighlight();

            activeHubId = hubId; // Track the current selection to prevent late-arriving async updates

            // Expand the side panel
            drawer.classList.remove('w-0', 'border-transparent');
            drawer.classList.add('w-full', 'md:w-[675px]', 'border-slate-100');

            // Highlight the active marker and reset others
            markers.forEach(m => {{
                const isSelected = m.id === hubId;
                if (m.content) {{
                    m.content.scale = isSelected ? 1.5 : 1.0;
                    m.content.borderColor = isSelected ? '#0f172a' : '#ffffff'; // Dark slate border for selection
                }}
                m.zIndex = isSelected ? 1000 : null;
            }});

            // Center the map on the hub point
            const hub = hubs.find(h => h.id === hubId);
            if (hub && map) {{
                map.panTo({{ lat: hub.lat, lng: hub.lng }});
                map.setZoom(7);
            }}
            
            // Use the pretty name directly from the map marker
            const prettyName = hubCity;

            // Immediately show the hub name and skeletons to improve perceived performance
            content.innerHTML = `
                <div class="flex justify-between items-start mb-2 gap-4">
                    <div class="flex-grow">
                        <h2 class="text-3xl font-black text-slate-900">${{prettyName}}</h2>
                        <div id="region-badge-container" class="mt-2"></div>
                    </div>
                    <div id="hub-image-container" class="w-64 h-48 flex-shrink-0 bg-slate-100 rounded-2xl overflow-hidden flex items-center justify-center border border-slate-100">
                        <div class="animate-pulse w-full h-full bg-slate-200"></div>
                    </div>
                </div>

                <h3 class="text-lg font-black text-slate-900 mb-1">Sport Representation</h3>
                <div id="stats-container" class="grid grid-cols-2 gap-y-2 gap-x-4 mb-2">
                    <div class="col-span-2 flex items-center justify-center py-4">
                        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                </div>
                <div id="narrative-section-container"></div>
            `;
            
            try {{
                // Fetch stats for the sport grid
                const statsResponse = await fetch(`/api/v1/hubs/${{encodeURIComponent(hubId)}}/stats`, {{
                    headers: {{ 'Authorization': `Bearer {api_key}` }}
                }});
                if (!statsResponse.ok) throw new Error('Failed to fetch stats');
                const statsData = await statsResponse.json();
                
                const totalAthletes = statsData.statistics.reduce((acc, curr) => acc + curr.athlete_count, 0);
                
                // Inject the insights container with hub-specific context
                document.getElementById('narrative-section-container').innerHTML = `
                    <div id="narrative-container" class="bg-blue-50 p-4 rounded-2xl border border-blue-100 mb-4">
                        <h3 class="text-sm font-bold text-blue-900 mb-2 flex items-center"><span class="mr-2">✨</span> AI Insights</h3>
                        <p id="narrative-text" class="text-blue-900 leading-relaxed opacity-80 text-sm">Analyzing success patterns for ${{totalAthletes}} athletes in ${{prettyName}}...</p>
                    </div>
                `;

                const region = statsData.statistics[0]?.region || 'Global';
                
                const regionBadge = `<div class="inline-block px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold uppercase tracking-widest mb-2">${{region}} Region</div>`;
                document.getElementById('region-badge-container').innerHTML = regionBadge;

                const sportHtml = statsData.statistics.map(item => {{
                    // Normalize sport name to Title Case for display
                    const sportName = item.sport_name.toLowerCase().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
                    const isSelected = selectedSports.has(item.sport_name);
                    const cardClass = isSelected ? 'bg-blue-50 border-blue-500 ring-4 ring-blue-200 scale-[1.02] shadow-md z-10' : 'bg-slate-100 border-slate-200';
                    
                    const sportId = item.sport_name.toLowerCase().replace(/ /g, "_").replace(/\//g, "_");
                    const bucket = "{project_id}-hub-images";
                    const iconUrl = `https://storage.googleapis.com/${{bucket}}/sports/${{sportId}}.webp`;

                    return `
                        <div class="${{cardClass}} p-2.5 rounded-xl border flex justify-between items-center shadow-sm transition-all duration-300">
                            <div class="flex items-center truncate">
                                <div class="w-8 h-8 rounded-full bg-white border border-slate-200 overflow-hidden flex items-center justify-center p-1 shadow-sm flex-shrink-0">
                                    <img src="${{iconUrl}}" class="w-full h-full object-contain" onerror="this.parentElement.style.display='none'">
                                </div>
                                <div class="truncate pl-3">
                                    <span class="text-base font-bold text-slate-900 truncate block uppercase tracking-widest">${{sportName}}</span>
                                </div>
                            </div>
                            <div class="flex-shrink-0 ml-2">
                                <span class="flex items-center justify-center w-8 h-8 bg-blue-600 text-white rounded-full text-sm font-bold shadow-sm">${{item.athlete_count}}</span>
                            </div>
                        </div>
                    `;
                }}).join('');

                document.getElementById('stats-container').innerHTML = sportHtml;

                 // Fetch Hub Image lazily (moved to load earlier)
                fetch(`/api/v1/hubs/${{encodeURIComponent(hubId)}}/image?pretty_name=${{encodeURIComponent(prettyName)}}&region=${{encodeURIComponent(region)}}`, {{
                    headers: {{ 'Authorization': `Bearer {api_key}` }}
                }})
                    .then(res => res.json())
                    .then(data => {{
                        // Prevent race condition: only update if this hub is still the one selected
                        if (activeHubId !== hubId) return;

                        const imgContainer = document.getElementById('hub-image-container');
                        if (data && data.image_data) {{
                             const rawData = data.image_data.trim().replace(/^<|>$/g, '');
                             // Check if image_data is a GCS URL or a Base64 string
                            const src = (rawData.startsWith('http') || rawData.startsWith('https')) ? rawData : `data:image/png;base64,${{rawData}}`;
                            imgContainer.innerHTML = `<img src="${{src}}" class="w-full h-full object-cover">`;
                        }}
                    }})
                    .catch(err => {{
                        document.getElementById('hub-image-container').innerHTML = '<span class="text-slate-300">🏔️</span>';
                    }});

                // Check JS cache first
                if (narrativeCache[hubId]) {{
                    const el = document.getElementById('narrative-text');
                    if (el) el.innerHTML = narrativeCache[hubId];
                }} else {{
                    {ai_insights_service.get_insights_js(api_key)}
                }}
            }} catch (err) {{
                content.innerHTML = '<p class="text-red-500 font-bold text-center">Failed to load regional data.</p>';
            }}
        }}

        // Automatically cycle the featured hub highlight every 5 seconds when idle
        setInterval(highlightRandomHub, 5000);
    """