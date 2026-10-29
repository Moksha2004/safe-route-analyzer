export type RouteResult = {
  routeId: string;
  rank: number;
  rankScore: number;
  geometry: { type: 'LineString'; coordinates: [number, number][] };
  durationSeconds: number;
  distanceMeters: number;
  trafficDelaySeconds: number;
  trafficSemantics: string;
  departureTime?: string;
  estimatedArrivalTime?: string;
  nightActivityScore: number;
  streetLightingScore: number;
  streetLampCount: number;
  lampsPerKm: number;
  streetLamps: GeoJSON.FeatureCollection;
  poiFeatures: GeoJSON.FeatureCollection;
  incidentsAlongRoute: unknown[];
  navigationSteps: { instruction?: string; message?: string; routeOffsetInMeters?: number; point?: { latitude?: number; longitude?: number } }[];
  preferenceScore: number;
  preferenceMatches: string[];
  nightActivityBreakdown: { components: Record<string, number>; missingSignals: string[]; evidenceCoverage?: number };
  activitySummary: Record<string, Record<string, number>>;
  policeCount: number;
  residentialCoveragePercent: number;
  explanation: string | null;
  missingSignals: string[];
};

export type ParsedPreferences = {
  model?: string;
  multipliers?: Record<string, number>;
  priorities?: string[];
  source?: string;
};

export type AnalyzeResponse = {
  routes: RouteResult[];
  parsedPreferences: ParsedPreferences;
  safetyClaims: false;
  limitations: string[];
};

export async function analyze(payload: unknown): Promise<AnalyzeResponse> {
  const response = await fetch('/api/routes/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Route analysis failed' }));
    throw new Error(error.detail ?? 'Route analysis failed');
  }
  return response.json() as Promise<AnalyzeResponse>;
}
