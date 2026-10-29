import { Map as MapLibreMap, Marker, NavigationControl } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';
import { analyze, type ParsedPreferences, type RouteResult } from './api/analyze';
import { searchPlaces, type PlaceSuggestion } from './api/places';
import { DEFAULT_MAX_ROUTES, MAX_ROUTES, MIN_SEARCH_LENGTH, SEARCH_DEBOUNCE_MS } from './config';
import { createMap } from './map/createMap';
import { clearRemainingRoute, drawRoutes, showRemainingRoute, toggleLamps } from './map/layers';

const root = document.querySelector<HTMLDivElement>('#app');
if (!root) throw new Error('App root missing');

root.innerHTML = `
  <main class="shell">
    <header class="topbar">
      <a class="brand" href="#" aria-label="Safe Route home"><span class="brand-mark">S</span><span>safe<span class="brand-light">route</span></span></a>
      <div class="topbar-meta"><span class="live-dot"></span> BENGALURU · ACTIVITY-LED ROUTING</div>
      <button class="icon-button" id="about-button" aria-label="About this service">i</button>
    </header>
    <section class="map-stage">
      <div id="map" aria-label="Map of route options"></div>
      <div class="map-label"><span class="map-label-dot"></span> Bengaluru, Karnataka</div>
      <form class="search-card" id="route-form">
        <div class="card-heading"><div><span class="eyebrow">PLAN YOUR JOURNEY</span><h1>Choose a route<br/>with more going on.</h1></div><span class="compass">✳</span></div>
        <div class="place-field"><label class="field-label" for="start">FROM</label><div class="input-wrap"><span class="pin origin"></span><input id="start" placeholder="Search for a place or address" autocomplete="off" required /><button class="locate-button" id="locate-button" type="button" title="Use my current location" aria-label="Use my current location">◎</button><button class="map-pick-button" id="pick-start" type="button" title="Choose starting point on map" aria-label="Choose starting point on map">Map</button></div><div class="place-suggestions" id="start-suggestions" role="listbox"></div></div>
        <div class="place-field"><label class="field-label" for="destination">TO</label><div class="input-wrap"><span class="pin destination-pin"></span><input id="destination" placeholder="Search for a place or address" autocomplete="off" required /><button class="map-pick-button" id="pick-destination" type="button" title="Choose destination on map" aria-label="Choose destination on map">Map</button></div><div class="place-suggestions" id="destination-suggestions" role="listbox"></div></div>
        <div class="form-row"><label class="select-field"><span class="field-label">TRAVEL MODE</span><select id="mode"><option value="car">Driving</option><option value="pedestrian">Walking</option><option value="bicycle">Cycling</option></select></label><label class="select-field"><span class="field-label" for="departure">DEPARTURE · LOCAL TIME</span><input class="datetime-input" id="departure" type="datetime-local" required /></label></div>
        <label class="field-label" for="route-count">ROUTE OPTIONS</label><select id="route-count" class="route-count-select">${Array.from({ length: MAX_ROUTES }, (_, index) => index + 1).map((count) => `<option value="${count}" ${count === DEFAULT_MAX_ROUTES ? 'selected' : ''}>Up to ${count} ${count === 1 ? 'route' : 'routes'}</option>`).join('')}</select>
        <label class="field-label" for="preferences">WHAT MATTERS TO YOU? <span class="optional">OPTIONAL</span></label><textarea id="preferences" rows="2" placeholder="Open shops, hospitals, street lighting…"></textarea>
        <button class="primary-button" id="submit-button" type="submit"><span>Find my routes</span><span aria-hidden="true">↗</span></button>
        <p class="quiet-note">Activity signals help compare routes. This is not a safety guarantee.</p>
      </form>
      <button class="map-control" id="lamp-toggle" type="button"><span class="lamp-symbol">✦</span><span>Street lamps</span><span class="toggle"></span></button>
      <div class="map-pick-banner" id="map-pick-banner" role="status"><span id="map-pick-message">Click on the map to choose a location.</span><button id="cancel-pick" type="button">Cancel</button></div>
      <div class="map-legend"><span class="legend-line"></span><span>Route options</span><span class="legend-lamp"></span><span>Mapped lamps</span></div>
      <section class="results-panel" id="results-panel" aria-live="polite">
        <div class="results-empty"><span class="empty-icon">↗</span><h2>Your routes, with context.</h2><p>Compare night activity, mapped lighting and route details once you search.</p></div>
      </section>
      <div class="map-error" id="map-error" role="status"></div>
    </section>
    <footer class="footer"><span>Designed for clearer choices, not safety promises.</span><span>Data: TomTom · OpenStreetMap</span></footer>
    <dialog id="about-dialog"><button class="dialog-close" id="close-dialog" aria-label="Close">×</button><span class="eyebrow">A NOTE ON THE DATA</span><h2>Evidence, not guarantees.</h2><p>Night activity scores combine mapped street lamps, nearby amenities, residential coverage and traffic signals. OpenStreetMap lighting is incomplete in many places, and a mapped lamp does not confirm that it is working.</p><p>We do not use crime data or claim any route is safe. Missing data is shown as a limitation—not as proof of risk.</p></dialog>
  </main>`;

const map = createMap(document.querySelector<HTMLElement>('#map')!);
const form = document.querySelector<HTMLFormElement>('#route-form')!;
const panel = document.querySelector<HTMLElement>('#results-panel')!;
const button = document.querySelector<HTMLButtonElement>('#submit-button')!;
const status = document.querySelector<HTMLElement>('#map-error')!;
let activeRoutes: RouteResult[] = [];
let activeParsed: ParsedPreferences = {};
let selectedIndex = 0;
let lampsVisible = false;
let pinMode = false;
let pinTarget: 'start' | 'destination' | null = null;
let startPin: { lat: number; lon: number } | null = null;
let destinationPin: { lat: number; lon: number } | null = null;
const pinMarkers: Marker[] = [];
let navigationWatchId: number | null = null;
let navigationMarker: Marker | null = null;
let navigationFollow = true;
const suggestionState: Record<'start' | 'destination', { timer: number | undefined; controller: AbortController | null; results: PlaceSuggestion[] }> = {
  start: { timer: undefined, controller: null, results: [] },
  destination: { timer: undefined, controller: null, results: [] },
};

map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
map.on('load', () => map.resize());
window.addEventListener('resize', () => map.resize());

function selectMapTarget(target: 'start' | 'destination'): void {
  pinMode = true;
  pinTarget = target;
  document.querySelector('#pick-start')?.classList.toggle('is-active', target === 'start');
  document.querySelector('#pick-destination')?.classList.toggle('is-active', target === 'destination');
  document.querySelector('#map')?.classList.add('is-picking-location');
  document.querySelector('.map-stage')?.classList.add('is-picking-location');
  document.querySelector<HTMLElement>('#map-pick-message')!.textContent = `Click the map to set your ${target === 'start' ? 'starting point' : 'destination'}.`;
  document.querySelector<HTMLElement>('#map-pick-banner')?.classList.add('visible');
  status.textContent = '';
}

document.querySelector('#pick-start')?.addEventListener('click', () => selectMapTarget('start'));
document.querySelector('#pick-destination')?.addEventListener('click', () => selectMapTarget('destination'));
document.querySelector('#cancel-pick')?.addEventListener('click', () => {
  pinMode = false;
  pinTarget = null;
  document.querySelector('#pick-start')?.classList.remove('is-active');
  document.querySelector('#pick-destination')?.classList.remove('is-active');
  document.querySelector('#map')?.classList.remove('is-picking-location');
  document.querySelector('.map-stage')?.classList.remove('is-picking-location');
  document.querySelector('#map-pick-banner')?.classList.remove('visible');
});

document.querySelector('#locate-button')?.addEventListener('click', () => {
  if (!navigator.geolocation) {
    status.textContent = 'Current location is unavailable in this browser. Choose a point on the map instead.';
    return;
  }
  const locateButton = document.querySelector<HTMLButtonElement>('#locate-button')!;
  locateButton.disabled = true;
  status.textContent = 'Getting your current location…';
  navigator.geolocation.getCurrentPosition((position) => {
    startPin = { lat: position.coords.latitude, lon: position.coords.longitude };
    document.querySelector<HTMLInputElement>('#start')!.value = 'Current location';
    hideSuggestions('start');
    updatePinMarkers();
    map.flyTo({ center: [startPin.lon, startPin.lat], zoom: 15, essential: true });
    status.textContent = `Current location set (accuracy ±${Math.round(position.coords.accuracy)} m).`;
    locateButton.disabled = false;
  }, (error) => {
    status.textContent = error.code === error.PERMISSION_DENIED
      ? 'Location permission was denied. Allow it in browser settings, or choose a point on the map.'
      : 'Could not determine your location. Try again or choose a point on the map.';
    locateButton.disabled = false;
  }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 30000 });
});

map.on('click', (event) => {
  if (!pinMode || !pinTarget) return;
  const selectedTarget = pinTarget;
  const point = { lat: Number(event.lngLat.lat.toFixed(6)), lon: Number(event.lngLat.lng.toFixed(6)) };
  if (selectedTarget === 'start') {
    startPin = point;
    document.querySelector<HTMLInputElement>('#start')!.value = `${point.lat}, ${point.lon}`;
    status.textContent = 'Starting point set from map.';
  } else {
    destinationPin = point;
    document.querySelector<HTMLInputElement>('#destination')!.value = `${point.lat}, ${point.lon}`;
    status.textContent = 'Destination set from map.';
  }
  pinMode = false;
  pinTarget = null;
  document.querySelector('#pick-start')?.classList.remove('is-active');
  document.querySelector('#pick-destination')?.classList.remove('is-active');
  document.querySelector('#map')?.classList.remove('is-picking-location');
  document.querySelector('.map-stage')?.classList.remove('is-picking-location');
  document.querySelector('#map-pick-banner')?.classList.remove('visible');
  updatePinMarkers();
  hideSuggestions(selectedTarget);
});

function updatePinMarkers(): void {
  pinMarkers.forEach((marker) => marker.remove());
  pinMarkers.length = 0;
  if (startPin) pinMarkers.push(new Marker({ color: '#087f72' }).setLngLat([startPin.lon, startPin.lat]).addTo(map));
  if (destinationPin) pinMarkers.push(new Marker({ color: '#dd9f41' }).setLngLat([destinationPin.lon, destinationPin.lat]).addTo(map));
}

function hideSuggestions(target: 'start' | 'destination'): void {
  const element = document.querySelector<HTMLElement>(`#${target}-suggestions`)!;
  element.innerHTML = '';
  element.classList.remove('visible');
  suggestionState[target].results = [];
  suggestionState[target].controller?.abort();
}

function showSuggestions(target: 'start' | 'destination', results: PlaceSuggestion[]): void {
  const element = document.querySelector<HTMLElement>(`#${target}-suggestions`)!;
  suggestionState[target].results = results;
  if (!results.length) {
    element.innerHTML = '<div class="suggestion-empty">No matching places found. You can still submit the typed address.</div>';
  } else {
    element.innerHTML = results.map((place, index) => `<button class="suggestion-option" type="button" role="option" data-place-index="${index}"><span class="suggestion-marker">⌖</span><span><strong>${escapeHtml(place.label)}</strong><small>${escapeHtml(place.address || `${place.lat.toFixed(5)}, ${place.lon.toFixed(5)}`)}</small></span></button>`).join('');
    element.querySelectorAll<HTMLButtonElement>('[data-place-index]').forEach((option) => option.addEventListener('click', () => {
      const selected = suggestionState[target].results[Number(option.dataset.placeIndex)];
      if (!selected) return;
      if (target === 'start') startPin = { lat: selected.lat, lon: selected.lon };
      else destinationPin = { lat: selected.lat, lon: selected.lon };
      document.querySelector<HTMLInputElement>(`#${target}`)!.value = selected.label;
      updatePinMarkers();
      map.flyTo({ center: [selected.lon, selected.lat], zoom: 14, essential: true });
      hideSuggestions(target);
      status.textContent = `${target === 'start' ? 'Starting point' : 'Destination'} selected from TomTom map search.`;
    }));
  }
  element.classList.add('visible');
}

function attachPlaceAutocomplete(target: 'start' | 'destination'): void {
  const input = document.querySelector<HTMLInputElement>(`#${target}`)!;
  input.addEventListener('input', () => {
    if (target === 'start') startPin = null;
    else destinationPin = null;
    updatePinMarkers();
    const state = suggestionState[target];
    window.clearTimeout(state.timer);
    state.controller?.abort();
    const query = input.value.trim();
    if (query.length < MIN_SEARCH_LENGTH) {
      hideSuggestions(target);
      return;
    }
    state.timer = window.setTimeout(async () => {
      const controller = new AbortController();
      state.controller = controller;
      try {
        const center = map.getCenter();
        const nearby = startPin ?? { lat: center.lat, lon: center.lng };
        const results = await searchPlaces(query, nearby, controller.signal);
        if (input.value.trim() === query) showSuggestions(target, results);
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        if (input.value.trim() === query) {
          const suggestionList = document.querySelector<HTMLElement>(`#${target}-suggestions`)!;
          suggestionList.innerHTML = '<div class="suggestion-empty">Map search is unavailable. You can still submit the typed address.</div>';
          suggestionList.classList.add('visible');
        }
      }
    }, SEARCH_DEBOUNCE_MS);
  });
  input.addEventListener('focus', () => {
    if (suggestionState[target].results.length) document.querySelector(`#${target}-suggestions`)?.classList.add('visible');
  });
}

attachPlaceAutocomplete('start');
attachPlaceAutocomplete('destination');

function localDateTimeValue(date: Date): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

const departureInput = document.querySelector<HTMLInputElement>('#departure')!;
departureInput.value = localDateTimeValue(new Date());
departureInput.addEventListener('change', () => {
  departureInput.setCustomValidity(departureInput.value ? '' : 'Choose a departure date and time.');
});

document.querySelector('#lamp-toggle')?.addEventListener('click', () => {
  lampsVisible = !lampsVisible;
  toggleLamps(map, lampsVisible);
  document.querySelector('#lamp-toggle')?.classList.toggle('is-active', lampsVisible);
});

document.querySelector('#about-button')?.addEventListener('click', () => document.querySelector<HTMLDialogElement>('#about-dialog')?.showModal());
document.querySelector('#close-dialog')?.addEventListener('click', () => document.querySelector<HTMLDialogElement>('#about-dialog')?.close());

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (navigationWatchId !== null) stopNavigation();
  status.textContent = '';
  button.disabled = true;
  button.innerHTML = '<span class="spinner"></span><span>Finding routes…</span>';
  const departureDate = new Date(departureInput.value);
  if (!departureInput.value || Number.isNaN(departureDate.getTime())) {
    status.textContent = 'Choose a valid departure date and time.';
    button.disabled = false;
    button.innerHTML = '<span>Find my routes</span><span aria-hidden="true">↗</span>';
    return;
  }
  try {
    const result = await analyze({
      start: startPin ?? document.querySelector<HTMLInputElement>('#start')!.value,
      destination: destinationPin ?? document.querySelector<HTMLInputElement>('#destination')!.value,
      mode: document.querySelector<HTMLSelectElement>('#mode')!.value,
      maxRoutes: Number(document.querySelector<HTMLSelectElement>('#route-count')!.value),
      departureTime: departureDate.toISOString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Kolkata',
      preferences: document.querySelector<HTMLTextAreaElement>('#preferences')!.value || null,
      explain: true,
    });
    activeRoutes = result.routes;
    activeParsed = result.parsedPreferences ?? {};
    selectedIndex = 0;
    if (!activeRoutes.length) throw new Error('No routes were returned. Try another destination.');
    renderResults(activeRoutes, result.limitations, result.parsedPreferences);
    drawRoutes(map, activeRoutes, selectedIndex);
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : 'Unable to analyze this journey.';
  } finally {
    button.disabled = false;
    button.innerHTML = '<span>Find my routes</span><span aria-hidden="true">↗</span>';
  }
});

const FACTOR_LABELS: Record<string, string> = {
  nas: 'Night activity',
  light: 'Street lighting',
  police: 'Police',
  hospital: 'Open hospitals',
  shop: 'Open shops',
  residential: 'Residential',
  delay: 'Less traffic',
  closure: 'Avoid closures',
  duration: 'Shorter trip',
};

function renderParsedPreferences(parsed: ParsedPreferences): string {
  const adjusted = Object.entries(parsed.multipliers ?? {}).filter(([, value]) => value !== 1).sort(([, a], [, b]) => b - a);
  if (parsed.source !== 'nebius' || !adjusted.length) return '';
  const chips = adjusted.map(([key, value]) => `<span>${value > 1 ? '▲' : '▼'} ${escapeHtml(FACTOR_LABELS[key] ?? key)} ×${value.toFixed(2)}</span>`).join('');
  return `<div class="preference-matches ai-preferences"><span>NEMOTRON NANO READ YOUR PREFERENCES AS</span><div class="signal-chips">${chips}</div></div>`;
}

function renderResults(routes: RouteResult[], limitations: string[], parsed: ParsedPreferences): void {
  const cards = routes.map((route, index) => {
    const components = route.nightActivityBreakdown.components ?? {};
    const missing = new Set([...route.missingSignals, ...(route.nightActivityBreakdown.missingSignals ?? [])]);
    const hasNasEvidence = Object.keys(components).length > 0;
    const score = Math.round(route.nightActivityScore);
    const lightScore = Math.round(route.streetLightingScore);
    const formatSignal = (signal: string, value: string): string => missing.has(signal) ? '—' : value;
    const active = index === selectedIndex;
    return `<button class="route-card ${active ? 'selected' : ''}" data-route-index="${index}" type="button">
      <div class="route-card-top"><span class="route-rank">0${route.rank}</span><span class="route-label">${route.rank === 1 ? 'BEST MATCH' : `ALTERNATIVE ${route.rank - 1}`}</span><span class="route-arrow">↗</span></div>
      <div class="score-row"><div><strong class="score-number">${hasNasEvidence ? score : '—'}</strong><span class="score-outof">${hasNasEvidence ? ' / 100' : ''}</span><div class="score-caption">${hasNasEvidence ? `Night activity score · ${Math.round(route.nightActivityBreakdown.evidenceCoverage ?? 0)}% of signals known` : 'Not enough mapped activity data'}</div></div><div class="score-ring" style="--score:${hasNasEvidence ? score * 3.6 : 0}deg"><span>${hasNasEvidence ? score : '—'}</span></div></div>
      <div class="metrics"><div class="metric"><span class="metric-icon">✦</span><span><strong>${formatSignal('streetLighting', String(lightScore))}<small>${missing.has('streetLighting') ? '' : '/100'}</small></strong><em>Mapped lighting</em></span></div><div class="metric"><span class="metric-icon">◷</span><span><strong>${formatDuration(route.durationSeconds)}</strong><em>Est. time · ${formatTime(route.estimatedArrivalTime)}</em></span></div><div class="metric"><span class="metric-icon">⌁</span><span><strong>${(route.distanceMeters / 1000).toFixed(1)}<small> km</small></strong><em>${formatSignal('traffic', `Delay ${formatDuration(route.trafficDelaySeconds)}`)}</em></span></div></div>
      <div class="breakdown"><span>ACTIVITY SIGNALS</span><div class="signal-chips"><span>Police ${formatSignal('police', String(Math.round(components.policePresence ?? route.policeCount * 50)))}</span><span>Shops ${missing.has('shops') ? '—' : `${route.activitySummary.shops?.open ?? 0} open${route.activitySummary.shops?.unknown ? ` · ${route.activitySummary.shops.unknown} unknown` : ''}`}</span><span>Hospitals ${missing.has('hospitals') ? '—' : `${route.activitySummary.hospitals?.open ?? 0} open${route.activitySummary.hospitals?.unknown ? ` · ${route.activitySummary.hospitals.unknown} unknown` : ''}`}</span><span>Homes ${formatSignal('residential', `${Math.round(route.residentialCoveragePercent)}%`)}</span></div></div>
      ${route.preferenceMatches.length ? `<div class="preference-matches"><span>YOUR PREFERENCES</span><div class="signal-chips">${route.preferenceMatches.map((match) => `<span>✓ ${escapeHtml(match)}</span>`).join('')}</div></div>` : ''}
      ${route.explanation ? `<p class="route-explanation"><span class="ai-label">NEMOTRON SUPER</span>${escapeHtml(route.explanation)}</p>` : ''}
      ${route.missingSignals.length ? `<p class="missing-note">Limited data: ${escapeHtml(route.missingSignals.join(', '))}</p>` : ''}
    </button>`;
  }).join('');
  const selectedRoute = routes[selectedIndex];
  const navigating = navigationWatchId !== null;
  panel.innerHTML = `<div class="results-header"><div><span class="eyebrow">YOUR ROUTES</span><h2>${routes.length} options to compare</h2></div><span class="sort-label">RANKED BY ACTIVITY</span></div>${renderParsedPreferences(parsed)}<div class="route-list">${cards}</div><section class="navigation-card"><div class="navigation-heading"><span class="navigation-icon">➤</span><span><strong>${navigating ? 'Navigation active' : `Navigate Route ${selectedRoute.rank}`}</strong><small id="navigation-status">${navigating ? 'Waiting for GPS…' : 'Follow the selected route with live location.'}</small></span></div><div class="navigation-progress"><span>REMAINING</span><strong id="navigation-distance">—</strong></div><button class="navigation-button ${navigating ? 'navigating' : ''}" id="navigation-button" type="button">${navigating ? 'Stop navigation' : 'Start navigation'}</button></section><div class="data-note"><span>ⓘ</span><p>${escapeHtml(limitations[1] ?? 'Scores describe mapped activity signals—not safety.')}</p></div>`;
  panel.querySelectorAll<HTMLButtonElement>('[data-route-index]').forEach((card) => card.addEventListener('click', () => {
    if (navigationWatchId !== null) stopNavigation();
    selectedIndex = Number(card.dataset.routeIndex ?? 0);
    renderResults(routes, limitations, parsed);
    drawRoutes(map, routes, selectedIndex);
  }));
  panel.querySelector<HTMLButtonElement>('#navigation-button')?.addEventListener('click', () => {
    if (navigationWatchId !== null) stopNavigation();
    else startNavigation();
  });
}

function startNavigation(): void {
  if (!navigator.geolocation) {
    status.textContent = 'Live location is not supported by this browser.';
    return;
  }
  if (!activeRoutes[selectedIndex]) return;
  navigationFollow = true;
  const button = panel.querySelector<HTMLButtonElement>('#navigation-button');
  if (button) {
    button.disabled = true;
    button.textContent = 'Connecting to GPS…';
  }
  status.textContent = 'Allow location access to start live route tracking.';
  navigationWatchId = navigator.geolocation.watchPosition(onNavigationPosition, (error) => {
    navigationWatchId = null;
    status.textContent = error.code === error.PERMISSION_DENIED
      ? 'Location permission denied. Enable it in browser settings to navigate live.'
      : 'Could not get a live GPS location. Check your signal and try again.';
    renderResults(activeRoutes, [], activeParsed);
  }, { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 });
}

function onNavigationPosition(position: GeolocationPosition): void {
  const location: [number, number] = [position.coords.longitude, position.coords.latitude];
  if (!navigationMarker) {
    const markerElement = document.createElement('div');
    markerElement.className = 'navigation-marker';
    navigationMarker = new Marker({ element: markerElement, anchor: 'center' }).setLngLat(location).addTo(map);
  } else {
    navigationMarker.setLngLat(location);
  }
  const route = activeRoutes[selectedIndex];
  if (!route) return;
  const remainingMeters = showRemainingRoute(map, route, location);
  if (navigationFollow) map.easeTo({ center: location, duration: 700, essential: true, ...(typeof position.coords.heading === 'number' ? { bearing: position.coords.heading } : {}) });
  const distance = panel.querySelector<HTMLElement>('#navigation-distance');
  const message = panel.querySelector<HTMLElement>('#navigation-status');
  if (distance) distance.textContent = formatDistance(remainingMeters);
  const traveledMeters = Math.max(0, route.distanceMeters - remainingMeters);
  const nextStep = route.navigationSteps.find((step) => Number(step.routeOffsetInMeters ?? 0) >= traveledMeters);
  if (message) message.textContent = nextStep?.instruction ?? nextStep?.message
    ? `Next: ${nextStep.instruction ?? nextStep.message} · GPS ±${Math.round(position.coords.accuracy)} m`
    : `Live location · GPS accuracy ±${Math.round(position.coords.accuracy)} m`;
  const button = panel.querySelector<HTMLButtonElement>('#navigation-button');
  if (button) {
    button.disabled = false;
    button.textContent = 'Stop navigation';
    button.classList.add('navigating');
  }
}

function stopNavigation(): void {
  if (navigationWatchId !== null) navigator.geolocation.clearWatch(navigationWatchId);
  navigationWatchId = null;
  navigationMarker?.remove();
  navigationMarker = null;
  clearRemainingRoute(map);
  if (activeRoutes.length) renderResults(activeRoutes, [], activeParsed);
}

function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  return minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}m` : `${minutes} min`;
}

function formatDistance(meters: number): string {
  return meters >= 1000 ? `${(meters / 1000).toFixed(1)} km` : `${meters} m`;
}

function formatTime(value?: string): string {
  if (!value) return 'arrival time unavailable';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'arrival time unavailable';
  return date.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character] ?? character);
}
