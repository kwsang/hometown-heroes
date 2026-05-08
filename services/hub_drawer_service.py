from services import ai_insights_service

def get_drawer_html() -> str:
    """Returns the HTML structure for the hub details side drawer."""
    return """
        <!-- Details Drawer -->
        <div id="drawer" class="w-0 transition-all duration-500 ease-in-out overflow-y-auto border-l border-transparent bg-white h-full relative">
            <div class="p-8 sticky top-0 bg-white/90 backdrop-blur-sm z-20 border-b border-slate-50">
                <button onclick="closeDrawer()" class="text-slate-400 hover:text-slate-900 font-bold uppercase text-xs tracking-widest flex items-center transition group">
                    <span class="mr-2 text-lg group-hover:-translate-x-1 transition-transform">✕</span> Close Details
                </button>
            </div>
            <div id="drawer-content" class="p-8 pt-2">
                <!-- Content injected via JS -->
            </div>
        </div>
    """

def get_drawer_js() -> str:
    """Returns the JavaScript logic for opening, closing, and populating the hub details drawer."""
    return """
        function closeDrawer() {
            const drawer = document.getElementById('drawer');
            drawer.classList.remove('w-full', 'md:w-[675px]', 'border-slate-100');
            drawer.classList.add('w-0', 'border-transparent');
            document.body.style.overflow = 'auto';
        }

        async function openDrawer(hubId, hubCity) {
            const drawer = document.getElementById('drawer');
            const content = document.getElementById('drawer-content');
            
            // Expand the side panel
            drawer.classList.remove('w-0', 'border-transparent');
            drawer.classList.add('w-full', 'md:w-[675px]', 'border-slate-100');

            // Center the map on the hub point
            const hub = hubs.find(h => h.id === hubId);
            if (hub && map) {
                map.panTo({ lat: hub.lat, lng: hub.lng });
                map.setZoom(7);
            }
            
            // Use the pretty name directly from the map marker
            const prettyName = hubCity;

            // Immediately show the hub name and skeletons to improve perceived performance
            content.innerHTML = `
                <div class="flex justify-between items-start mb-6 gap-4">
                    <div class="flex-grow">
                        <h2 class="text-3xl font-black text-slate-900">${prettyName}</h2>
                    </div>
                    <div id="hub-image-container" class="w-72 h-48 flex-shrink-0 bg-slate-100 rounded-2xl overflow-hidden flex items-center justify-center border border-slate-100">
                        <div class="animate-pulse w-full h-full bg-slate-200"></div>
                    </div>
                </div>

                <h3 class="text-lg font-black text-slate-900 mb-4">Sport Representation</h3>
                <div id="stats-container" class="grid grid-cols-2 gap-3 mb-8">
                    <div class="col-span-2 flex items-center justify-center py-12">
                        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                    </div>
                </div>
                """ + ai_insights_service.get_insights_html() + """
            `;
            
            try {
                // Fetch stats for the sport grid
                const statsResponse = await fetch(`/api/v1/hubs/${hubId}/stats`);
                if (!statsResponse.ok) throw new Error('Failed to fetch stats');
                const statsData = await statsResponse.json();
                
                const region = statsData.statistics[0]?.region || 'Global';

                // Add the region badge above the name
                const regionBadge = `<div class="inline-block px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-bold uppercase tracking-widest mb-4">${region} Region</div>`;
                content.insertAdjacentHTML('afterbegin', regionBadge);

                const sportHtml = statsData.statistics.map(item => `
                    <div class="bg-slate-50 p-3 rounded-xl border border-slate-100 flex justify-between items-center">
                        <div class="truncate mr-2">
                            <span class="block text-xs font-bold text-slate-400 uppercase tracking-widest mb-1">Sport</span>
                            <span class="text-sm font-black text-slate-900 truncate block">${item.sport_name}</span>
                        </div>
                        <div class="text-right flex-shrink-0">
                            <span class="inline-block px-2 py-0.5 bg-blue-600 text-white rounded-lg text-xs font-bold">${item.athlete_count}</span>
                        </div>
                    </div>
                `).join('');

                document.getElementById('stats-container').innerHTML = sportHtml;

                 // Fetch Hub Image lazily (moved to load earlier)
                fetch(`/api/v1/hubs/${hubId}/image?pretty_name=${encodeURIComponent(prettyName)}&region=${encodeURIComponent(region)}`)
                    .then(res => res.json())
                    .then(data => {
                        const imgContainer = document.getElementById('hub-image-container');
                        if (data.image_data) {
                            imgContainer.innerHTML = `<img src="data:image/png;base64,${data.image_data}" class="w-full h-full object-cover">`;
                        }
                    })
                    .catch(err => {
                        document.getElementById('hub-image-container').innerHTML = '<span class="text-slate-300">🏔️</span>';
                    });

                // Fetch narrative lazily to prioritize UI responsiveness
                fetch(`/api/v1/hubs/${hubId}/narrative`)
                    .then(res => res.json())
                    .then(data => {
                        const narrativeEl = document.getElementById('narrative-text');
                        if (narrativeEl) {
                            narrativeEl.classList.remove('animate-pulse');
                            narrativeEl.innerHTML = `"${data.narrative}"`; // Use innerHTML to render bold text
                        }
                    })
                    .catch(err => {
                        const narrativeEl = document.getElementById('narrative-text');
                        if (narrativeEl) {
                            narrativeEl.classList.remove('animate-pulse');
                            narrativeEl.innerText = "Regional insights are currently unavailable.";
                        }
                    });

            } catch (err) {
                content.innerHTML = '<p class="text-red-500 font-bold text-center">Failed to load regional data.</p>';
            }
        }
    """