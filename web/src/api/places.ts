export type PlaceSuggestion = {
  id: string;
  label: string;
  address: string;
  lat: number;
  lon: number;
};

export async function searchPlaces(query: string, near: { lat: number; lon: number }, signal?: AbortSignal): Promise<PlaceSuggestion[]> {
  const params = new URLSearchParams({ q: query, lat: String(near.lat), lon: String(near.lon) });
  const response = await fetch(`/api/places/search?${params}`, { signal });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Place search is unavailable' }));
    throw new Error(error.detail ?? 'Place search is unavailable');
  }
  const result = await response.json() as { results: PlaceSuggestion[] };
  return result.results;
}
