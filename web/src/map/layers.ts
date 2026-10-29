import { LngLatBounds, type Map, type GeoJSONSource } from 'maplibre-gl';
import type { RouteResult } from '../api/analyze';

const colors = ['#087f72', '#d79536', '#477aa5', '#a86545', '#738657'];

function featureCollection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: 'FeatureCollection', features };
}

export function drawRoutes(map: Map, routes: RouteResult[], selected: number): void {
  const routeFeatures: GeoJSON.Feature[] = routes.map((route, index) => ({
    type: 'Feature',
    properties: { routeId: route.routeId, rank: route.rank, color: colors[(route.rank - 1) % colors.length], selected: index === selected },
    geometry: route.geometry,
  }));
  const selectedFeature = routeFeatures.splice(selected, 1)[0];
  if (selectedFeature) routeFeatures.push(selectedFeature);
  const source = map.getSource('routes') as GeoJSONSource | undefined;
  if (source) source.setData(featureCollection(routeFeatures));
  else {
    map.addSource('routes', { type: 'geojson', data: featureCollection(routeFeatures) });
    map.addLayer({ id: 'route-casing', type: 'line', source: 'routes', paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 11, 0], 'line-opacity': 0.95, 'line-blur': 0.5 } });
    map.addLayer({ id: 'route-lines', type: 'line', source: 'routes', paint: { 'line-color': ['get', 'color'], 'line-width': ['case', ['get', 'selected'], 7, 3.5], 'line-opacity': ['case', ['get', 'selected'], 1, 0.72] } });
  }
  drawCombined(map, 'pois', routes.flatMap((route) => route.poiFeatures.features));
  drawCombined(map, 'lamps', routes.flatMap((route) => route.streetLamps.features));
  const incidentFeatures: GeoJSON.Feature[] = routes.flatMap((route) => route.incidentsAlongRoute.map((incident): GeoJSON.Feature | null => {
    const item = incident as { geometry?: { type?: string; coordinates?: unknown }; properties?: Record<string, unknown> };
    const geometry = item.geometry as GeoJSON.Geometry | undefined;
    return geometry ? { type: 'Feature' as const, properties: item.properties ?? {}, geometry } : null;
  }).filter((feature): feature is NonNullable<typeof feature> => feature !== null));
  drawCombined(map, 'incidents', incidentFeatures);
  fitRoute(map, routes[selected]);
}

export function showRemainingRoute(map: Map, route: RouteResult, location: [number, number]): number {
  const coordinates = route.geometry.coordinates;
  let nearestIndex = 0;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (let index = 0; index < coordinates.length; index += 1) {
    const [lon, lat] = coordinates[index];
    const distance = (lon - location[0]) ** 2 + (lat - location[1]) ** 2;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  }
  const remaining = coordinates.slice(nearestIndex);
  if (remaining.length === 1) remaining.push(remaining[0]);
  const feature: GeoJSON.Feature = { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: remaining } };
  const source = map.getSource('navigation-remaining') as GeoJSONSource | undefined;
  if (source) source.setData(feature);
  else {
    map.addSource('navigation-remaining', { type: 'geojson', data: feature });
    map.addLayer({ id: 'navigation-remaining-line', type: 'line', source: 'navigation-remaining', paint: { 'line-color': '#075e56', 'line-width': 8, 'line-opacity': 1, 'line-dasharray': [1.5, 1] } });
  }
  return lineLengthMeters(remaining);
}

function lineLengthMeters(coordinates: [number, number][]): number {
  let length = 0;
  for (let index = 1; index < coordinates.length; index += 1) {
    const [lon1, lat1] = coordinates[index - 1];
    const [lon2, lat2] = coordinates[index];
    const radians = Math.PI / 180;
    const dLat = (lat2 - lat1) * radians;
    const dLon = (lon2 - lon1) * radians;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * radians) * Math.cos(lat2 * radians) * Math.sin(dLon / 2) ** 2;
    length += 6_371_000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return Math.round(length);
}

export function clearRemainingRoute(map: Map): void {
  const source = map.getSource('navigation-remaining') as GeoJSONSource | undefined;
  source?.setData({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: [] } });
}

function drawCombined(map: Map, name: string, features: GeoJSON.Feature[]): void {
  const data = featureCollection(features);
  const source = map.getSource(name) as GeoJSONSource | undefined;
  if (source) source.setData(data);
  else {
    map.addSource(name, { type: 'geojson', data });
    const isLamp = name === 'lamps';
    const isIncident = name === 'incidents';
    map.addLayer({ id: `${name}-circles`, type: 'circle', source: name, paint: { 'circle-radius': isLamp ? 3 : 6, 'circle-color': isIncident ? '#c44936' : isLamp ? '#e7a93d' : '#167c72', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 1.2 }, layout: { visibility: isLamp ? 'none' : 'visible' } });
  }
}

function fitRoute(map: Map, route: RouteResult): void {
  if (!route?.geometry.coordinates.length) return;
  const coordinates = route.geometry.coordinates;
  const bounds = coordinates.reduce((result, coordinate) => result.extend(coordinate), new LngLatBounds(coordinates[0], coordinates[0]));
  map.fitBounds(bounds, { padding: { top: 56, bottom: 56, left: 56, right: 440 }, maxZoom: 15, duration: 700 });
}

export function toggleLamps(map: Map, visible: boolean): void {
  if (map.getLayer('lamps-circles')) map.setLayoutProperty('lamps-circles', 'visibility', visible ? 'visible' : 'none');
}
