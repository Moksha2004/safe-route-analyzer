import { Map as MapLibreMap, type Map } from 'maplibre-gl';
import { setWorkerUrl } from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';

setWorkerUrl(maplibreWorkerUrl);

const tomtomStyle = 'https://api.tomtom.com/map/1/style/2/basic_main/standard.json?key=';

export function createMap(container: HTMLElement): Map {
  const key = import.meta.env.VITE_TOMTOM_API_KEY as string | undefined;
  const style = key
    ? `${tomtomStyle}${encodeURIComponent(key)}`
    : 'https://tiles.openfreemap.org/styles/liberty';

  return new MapLibreMap({
    container,
    style,
    center: [77.638, 12.935],
    zoom: 11,
    attributionControl: {},
    maxZoom: 19,
  });
}
