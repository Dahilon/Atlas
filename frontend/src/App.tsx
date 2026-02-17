import { useEffect, useState, useCallback } from 'react';
import MapboxGlobe from './components/MapboxGlobe';
import Sidebar from './components/Sidebar';
import MoversTable from './components/MoversTable';
import CountryDrilldown from './components/CountryDrilldown';
import CountryPanel from './components/CountryPanel';
import BriefView from './components/BriefView';
import EvidencePanel from './components/EvidencePanel';
import AnalyticsView from './components/AnalyticsView';
import SummaryStatsBar from './components/SummaryStatsBar';
import {
  getMetrics,
  getSpikes,
  getBrief,
  getEvents,
  getCountries,
  getMap,
  getCombinedEvents,
  getMilitaryBases,
  type Metric,
  type Spike,
  type BriefResponse,
  type EventItem,
} from './api';
import { useEventsStore } from './stores/events-store';

type Tab = 'map' | 'analytics' | 'movers' | 'drilldown' | 'brief' | 'evidence';

export default function App() {
  const [tab, setTab] = useState<Tab>('map');
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [spikes, setSpikes] = useState<Spike[]>([]);
  const [brief, setBrief] = useState<BriefResponse | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [briefLoading, setBriefLoading] = useState(false);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [briefDate, setBriefDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [evidenceCountry, setEvidenceCountry] = useState<string>('');
  const [evidenceCategory, setEvidenceCategory] = useState<string>('');
  const [mapData, setMapData] = useState<Awaited<ReturnType<typeof getMap>>>([]);
  const [militaryBases, setMilitaryBases] = useState<Awaited<ReturnType<typeof getMilitaryBases>>['bases']>([]);
  const [mapLoading, setMapLoading] = useState(false);
  const [countryPanelCountry, setCountryPanelCountry] = useState<string | null>(null);
  const setMapEventsInStore = useEventsStore((s) => s.setEvents);

  // ── Load core data on mount ──
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [metricsRes, spikesRes, countriesRes] = await Promise.all([
        getMetrics(),
        getSpikes({ limit: '200' }),
        getCountries(),
      ]);
      setMetrics(metricsRes);
      setSpikes(spikesRes);
      setCountries(countriesRes.countries ?? []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Load map data on mount (always, since map is always visible) ──
  useEffect(() => {
    let cancelled = false;
    setMapLoading(true);
    Promise.all([getMap(), getCombinedEvents({ limit: '500' }), getMilitaryBases()])
      .then(([countries, combined, bases]) => {
        if (cancelled) return;
        setMapData(countries);
        setMapEventsInStore(combined.events);
        setMilitaryBases(bases.bases ?? []);
      })
      .catch(() => { if (!cancelled) { setMapData([]); setMapEventsInStore([]); setMilitaryBases([]); } })
      .finally(() => { if (!cancelled) setMapLoading(false); });
    return () => { cancelled = true; };
  }, [setMapEventsInStore]);

  // ── Brief data (lazy) ──
  useEffect(() => {
    if (tab !== 'brief') return;
    let cancelled = false;
    setBriefLoading(true);
    getBrief(briefDate)
      .then((b) => { if (!cancelled) setBrief(b); })
      .catch(() => { if (!cancelled) setBrief(null); })
      .finally(() => { if (!cancelled) setBriefLoading(false); });
    return () => { cancelled = true; };
  }, [tab, briefDate]);

  // ── Evidence data (lazy) ──
  useEffect(() => {
    if (tab !== 'evidence') return;
    let cancelled = false;
    setEvidenceLoading(true);
    const params: Record<string, string> = { limit: '100' };
    if (evidenceCountry) params.country = evidenceCountry;
    if (evidenceCategory) params.category = evidenceCategory;
    getEvents(params)
      .then((e) => { if (!cancelled) setEvents(e); })
      .catch(() => { if (!cancelled) setEvents([]); })
      .finally(() => { if (!cancelled) setEvidenceLoading(false); });
    return () => { cancelled = true; };
  }, [tab, evidenceCountry, evidenceCategory]);

  const nav: { id: Tab; label: string }[] = [
    { id: 'map', label: 'Map' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'movers', label: 'Movers' },
    { id: 'drilldown', label: 'Drilldown' },
    { id: 'brief', label: 'Brief' },
    { id: 'evidence', label: 'Evidence' },
  ];

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-slate-950 text-slate-200">
      {/* ── Background: Map (always rendered) ── */}
      <div className="fixed inset-0 z-0">
        <MapboxGlobe
          militaryBases={militaryBases}
          countryData={mapData}
          onCountrySelect={setCountryPanelCountry}
          onClearAll={() => setCountryPanelCountry(null)}
        />
      </div>

      {/* ── Floating Header ── */}
      <header className="fixed top-0 left-0 right-0 z-50 glass-heavy">
        <div className="flex items-center justify-between px-5 py-2.5">
          <h1 className="text-base font-bold tracking-tight text-slate-100">
            GERID
            <span className="ml-2 text-xs font-normal text-slate-500">Global Events Risk Intelligence</span>
          </h1>

          <nav className="flex items-center gap-1">
            {nav.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                  tab === id
                    ? 'bg-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.15)]'
                    : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
            <div className="ml-2 h-5 w-px bg-white/10" />
            {/* Country selector */}
            <select
              value={countryPanelCountry ?? ''}
              onChange={(e) => setCountryPanelCountry(e.target.value || null)}
              className="ml-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-xs text-slate-300 outline-none transition hover:bg-white/10"
            >
              <option value="">Country...</option>
              {countries.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => load()}
              className="ml-1 rounded-lg bg-white/5 px-3 py-1.5 text-xs text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
            >
              Refresh
            </button>
          </nav>
        </div>
      </header>

      {/* ── Error banner ── */}
      {error && (
        <div className="fixed top-14 left-1/2 z-50 -translate-x-1/2 rounded-xl border border-amber-500/30 bg-amber-900/80 px-4 py-2 text-sm text-amber-200 backdrop-blur">
          {error}
        </div>
      )}

      {/* ── Summary Stats (map tab only) ── */}
      {tab === 'map' && <SummaryStatsBar countryData={mapData} />}

      {/* ── Floating Sidebar (map tab only) ── */}
      <Sidebar visible={tab === 'map'} />

      {/* ── Country Panel (slide-in, any tab) ── */}
      {countryPanelCountry && (
        <CountryPanel country={countryPanelCountry} onClose={() => setCountryPanelCountry(null)} />
      )}

      {/* ── Tab Overlays (render on top of map) ── */}
      {tab === 'analytics' && (
        <AnalyticsView onClose={() => setTab('map')} />
      )}

      {tab === 'movers' && (
        <div className="fixed inset-0 z-20 overflow-y-auto pt-20 pb-8 px-6">
          <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => setTab('map')} />
          <div className="relative z-10 mx-auto max-w-5xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-100">Top Movers</h2>
              <button
                type="button"
                onClick={() => setTab('map')}
                className="rounded-xl glass px-3 py-1.5 text-sm text-slate-400 transition hover:text-slate-200"
              >
                Back to Map
              </button>
            </div>
            <div className="rounded-2xl glass-heavy p-5">
              <MoversTable
                metrics={metrics}
                onSelectCountry={(c) => {
                  setSelectedCountry(c);
                  setCountryPanelCountry(c);
                }}
              />
            </div>
          </div>
        </div>
      )}

      {tab === 'drilldown' && (
        <div className="fixed inset-0 z-20 overflow-y-auto pt-20 pb-8 px-6">
          <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => setTab('map')} />
          <div className="relative z-10 mx-auto max-w-5xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-100">Country Drilldown</h2>
              <button
                type="button"
                onClick={() => setTab('map')}
                className="rounded-xl glass px-3 py-1.5 text-sm text-slate-400 transition hover:text-slate-200"
              >
                Back to Map
              </button>
            </div>
            <div className="rounded-2xl glass-heavy p-5">
              <CountryDrilldown country={selectedCountry} metrics={metrics} spikes={spikes} />
            </div>
          </div>
        </div>
      )}

      {tab === 'brief' && (
        <div className="fixed inset-0 z-20 overflow-y-auto pt-20 pb-8 px-6">
          <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => setTab('map')} />
          <div className="relative z-10 mx-auto max-w-4xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-100">Daily Brief</h2>
              <button
                type="button"
                onClick={() => setTab('map')}
                className="rounded-xl glass px-3 py-1.5 text-sm text-slate-400 transition hover:text-slate-200"
              >
                Back to Map
              </button>
            </div>
            <div className="rounded-2xl glass-heavy p-5">
              <BriefView
                brief={brief}
                briefDate={briefDate}
                onDateChange={setBriefDate}
                loading={briefLoading}
              />
            </div>
          </div>
        </div>
      )}

      {tab === 'evidence' && (
        <div className="fixed inset-0 z-20 overflow-y-auto pt-20 pb-8 px-6">
          <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => setTab('map')} />
          <div className="relative z-10 mx-auto max-w-5xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-100">Evidence</h2>
              <button
                type="button"
                onClick={() => setTab('map')}
                className="rounded-xl glass px-3 py-1.5 text-sm text-slate-400 transition hover:text-slate-200"
              >
                Back to Map
              </button>
            </div>
            <div className="rounded-2xl glass-heavy p-5">
              <EvidencePanel
                events={events}
                loading={evidenceLoading}
                country={evidenceCountry || null}
                category={evidenceCategory || null}
                onCountryChange={setEvidenceCountry}
                onCategoryChange={setEvidenceCategory}
                countryOptions={countries}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
