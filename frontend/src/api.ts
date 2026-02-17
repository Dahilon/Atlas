const API_BASE = process.env.API_URL || 'http://localhost:8000';

async function fetchApi<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(path, API_BASE);
  if (params) {
    Object.entries(params).forEach(([k, v]) => v && url.searchParams.set(k, v));
  }
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export interface Metric {
  date: string;
  country: string;
  category: string;
  event_count: number;
  avg_tone: number | null;
  rolling_center?: number | null;
  rolling_dispersion?: number | null;
  baseline_quality?: string | null;
  baseline_method?: string | null;
  z_score?: number | null;
  risk_score?: number | null;
  reasons_json?: string | null;
  computed_at?: string | null;
  pipeline_version?: string | null;
}

export interface Spike {
  id: number;
  date: string;
  country: string;
  category: string;
  z_score: number;
  z_used?: number | null;
  delta?: number | null;
  rolling_center?: number | null;
  rolling_dispersion?: number | null;
  baseline_quality?: string | null;
  baseline_method?: string | null;
  evidence_event_ids?: string | null;
  computed_at?: string | null;
  pipeline_version?: string | null;
}

export interface BriefResponse {
  top_movers: Array<{
    date: string;
    country: string;
    category: string;
    risk_score?: number | null;
    event_count?: number;
    z_score?: number | null;
  }>;
  top_spikes: Array<{
    date: string;
    country: string;
    category: string;
    z_score?: number | null;
    z_used?: number | null;
    delta?: number | null;
  }>;
  summary: string;
}

export interface EventItem {
  id: string;
  ts: string;
  date: string;
  country: string | null;
  admin1: string | null;
  lat: number | null;
  lon: number | null;
  event_code: string | null;
  quad_class: number | null;
  avg_tone: number | null;
  source_url: string | null;
  category: string | null;
}

export async function getMetrics(params?: { country?: string; start?: string; end?: string; category?: string }): Promise<Metric[]> {
  return fetchApi<Metric[]>('/metrics', params as Record<string, string>);
}

export async function getSpikes(params?: { country?: string; category?: string; start?: string; end?: string; limit?: string }): Promise<Spike[]> {
  return fetchApi<Spike[]>('/spikes', params as Record<string, string>);
}

export async function getBrief(forDate?: string): Promise<BriefResponse> {
  return fetchApi<BriefResponse>('/brief', forDate ? { date: forDate } : undefined);
}

export async function getEvents(params?: { country?: string; start?: string; end?: string; category?: string; limit?: string }): Promise<EventItem[]> {
  return fetchApi<EventItem[]>('/events', params as Record<string, string>);
}

export async function getCountries(): Promise<{ countries: string[] }> {
  return fetchApi<{ countries: string[] }>('/countries');
}

// --- Map + combined events (MapEvent shape) ---

export type MapEventSource = 'gdelt' | 'valyu';
export type ThreatLevel = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type TrendDirection = 'rising' | 'stable' | 'falling';

export interface MapEventLocation {
  latitude: number;
  longitude: number;
  placeName?: string | null;
  country?: string | null;
  region?: string | null;
}

export interface MapEvent {
  id: string;
  source: MapEventSource;
  title: string;
  summary: string;
  category: string;
  threatLevel: ThreatLevel;
  location: MapEventLocation;
  timestamp: string;
  sourceUrl?: string | null;
  severity_index?: number | null;
  risk_score?: number | null;
  event_count?: number | null;
  // ML-enriched
  category_confidence?: number | null;
  sentiment_polarity?: number | null;
  entities?: {
    countries?: Array<{ name: string; code: string }>;
    organizations?: string[];
    persons?: string[];
    primary_country?: string | null;
  } | null;
}

export interface MapCountryItem {
  country: string;
  lat: number;
  lon: number;
  severity_index?: number | null;
  risk_score?: number | null;
  event_count?: number | null;
  // ML-enriched
  risk_tier?: ThreatLevel | null;
  risk_percentile?: number | null;
  trend_7d?: TrendDirection | null;
  trend_30d?: TrendDirection | null;
  avg_sentiment?: number | null;
  top_category?: string | null;
}

export interface CombinedEventsResponse {
  events: MapEvent[];
  count: number;
  sources: Record<string, number>;
}

export interface MilitaryBaseItem {
  country: string;
  baseName: string;
  latitude: number;
  longitude: number;
  type: string;
}

export async function getMap(date?: string): Promise<MapCountryItem[]> {
  return fetchApi<MapCountryItem[]>('/map', date ? { date } : undefined);
}

export async function getCombinedEvents(params?: { date?: string; sources?: string; limit?: string }): Promise<CombinedEventsResponse> {
  const p: Record<string, string> = {};
  if (params?.date) p.date = params.date;
  if (params?.sources) p.sources = params.sources;
  if (params?.limit) p.limit = params.limit;
  return fetchApi<CombinedEventsResponse>('/events/combined', Object.keys(p).length ? p : undefined);
}

export async function getMilitaryBases(): Promise<{ bases: MilitaryBaseItem[]; cached?: boolean }> {
  return fetchApi<{ bases: MilitaryBaseItem[]; cached?: boolean }>('/military-bases');
}

export interface ConflictSection {
  conflicts: string;
  sources: Array<Record<string, unknown>>;
}

export interface CountryConflictsResponse {
  country: string;
  past: ConflictSection;
  current: ConflictSection;
  timestamp?: string;
}

export async function getCountryConflicts(country: string): Promise<CountryConflictsResponse> {
  return fetchApi<CountryConflictsResponse>('/valyu/countries/conflicts', { country });
}

// --- Analytics API ---

export interface RiskDistribution {
  bins: Array<{ range: string; count: number }>;
  stats: {
    mean: number;
    median: number;
    std: number;
    min: number;
    max: number;
    count: number;
  };
}

export interface RiskTiers {
  method: string;
  boundaries: number[];
  tier_ranges: Record<string, [number, number]>;
  n_samples: number;
  fitted_at?: string | null;
}

export interface CategoryBreakdown {
  categories: Array<{ name: string; count: number; percentage: number }>;
  total: number;
}

export interface SparklineData {
  country: string;
  dates: string[];
  values: (number | null)[];
}

export interface TopMover {
  country: string;
  severity_index: number | null;
  risk_tier: ThreatLevel | null;
  risk_percentile: number | null;
  trend_7d: TrendDirection | null;
  event_count: number;
}

export async function getRiskDistribution(): Promise<RiskDistribution> {
  return fetchApi<RiskDistribution>('/analytics/risk-distribution');
}

export async function getRiskTiers(): Promise<RiskTiers> {
  return fetchApi<RiskTiers>('/analytics/risk-tiers');
}

export async function getCategoryBreakdown(days?: number): Promise<CategoryBreakdown> {
  return fetchApi<CategoryBreakdown>('/analytics/category-breakdown', days ? { days: String(days) } : undefined);
}

export async function getSparklines(countries: string[]): Promise<SparklineData[]> {
  return fetchApi<SparklineData[]>('/analytics/sparklines', { countries: countries.join(',') });
}

export async function getTopMovers(limit?: number): Promise<TopMover[]> {
  return fetchApi<TopMover[]>('/analytics/top-movers', limit ? { limit: String(limit) } : undefined);
}

// --- Country Insights API ---

export interface CountryInsightsEvent {
  id: string;
  title: string;
  category: string | null;
  threat_level: string;
  severity: number | null;
  sentiment: number | null;
  date: string;
  source_url: string | null;
  entities: Record<string, unknown> | null;
}

export interface CountryInsightsNews {
  title: string;
  url: string;
  date: string | null;
  source: string | null;
  category: string | null;
  confidence: number | null;
  severity: number | null;
  threat_level: string | null;
}

export interface CountryInsights {
  country: string;
  country_name: string;
  summary: {
    risk_tier: string;
    severity: number;
    trend: string;
    event_count: number;
    avg_sentiment: number | null;
  };
  risk_context: string;
  recent_events: CountryInsightsEvent[];
  recent_news: CountryInsightsNews[];
  category_breakdown: Record<string, number>;
  related_countries: string[];
  metrics_history: Array<{ date: string; severity: number; events: number }>;
}

export async function getCountryInsights(countryCode: string): Promise<CountryInsights> {
  return fetchApi<CountryInsights>(`/countries/${encodeURIComponent(countryCode)}/insights`);
}
