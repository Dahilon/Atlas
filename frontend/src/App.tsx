import { useEffect, useState, useCallback } from 'react';
import MapboxGlobe from './components/MapboxGlobe';
import Sidebar from './components/Sidebar';
import MoversTable from './components/MoversTable';
import CountryDrilldown from './components/CountryDrilldown';
import BriefView from './components/BriefView';
import EvidencePanel from './components/EvidencePanel';
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

type Tab = 'map' | 'movers' | 'drilldown' | 'brief' | 'evidence';

export default function App() {
  const [tab, setTab] = useState<Tab>('brief');
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
  const setMapEventsInStore = useEventsStore((s) => s.setEvents);

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

  useEffect(() => {
    load();
  }, [load]);

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

  useEffect(() => {
    if (tab !== 'map') return;
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
  }, [tab, setMapEventsInStore]);

  const nav = [
    { id: 'map' as Tab, label: 'Map' },
    { id: 'movers' as Tab, label: 'Movers' },
    { id: 'drilldown' as Tab, label: 'Drilldown' },
    { id: 'brief' as Tab, label: 'Brief' },
    { id: 'evidence' as Tab, label: 'Evidence' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      <header className="border-b border-slate-800 bg-slate-900/80 px-4 py-3">
        <h1 className="text-xl font-bold text-slate-100">Global Events Risk Intelligence Dashboard</h1>
        <nav className="mt-2 flex flex-wrap gap-2">
          {nav.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`rounded px-3 py-1.5 text-sm font-medium transition ${
                tab === id ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200'
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => load()}
            className="ml-auto rounded bg-slate-700 px-3 py-1.5 text-sm text-slate-300 hover:bg-slate-600"
          >
            Refresh
          </button>
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6">
        {error && (
          <div className="mb-4 rounded-lg border border-amber-700/50 bg-amber-900/20 px-4 py-2 text-amber-200">
            {error} — Is the API running at {process.env.API_URL || 'http://localhost:8000'}?
          </div>
        )}

        {loading && tab !== 'brief' && tab !== 'evidence' && (
          <p className="text-slate-400">Loading…</p>
        )}

        {tab === 'map' && (
          <div className="flex gap-0">
            <div className="min-w-0 flex-1">
              {mapLoading && (
                <p className="mb-2 text-slate-400">Loading map data…</p>
              )}
              <MapboxGlobe militaryBases={militaryBases} />
            </div>
            <Sidebar />
          </div>
        )}

        {tab === 'movers' && (
          <MoversTable
            metrics={metrics}
            onSelectCountry={(c) => { setSelectedCountry(c); setTab('drilldown'); }}
          />
        )}

        {tab === 'drilldown' && (
          <CountryDrilldown country={selectedCountry} metrics={metrics} spikes={spikes} />
        )}

        {tab === 'brief' && (
          <BriefView
            brief={brief}
            briefDate={briefDate}
            onDateChange={setBriefDate}
            loading={briefLoading}
          />
        )}

        {tab === 'evidence' && (
          <EvidencePanel
            events={events}
            loading={evidenceLoading}
            country={evidenceCountry || null}
            category={evidenceCategory || null}
            onCountryChange={setEvidenceCountry}
            onCategoryChange={setEvidenceCategory}
            countryOptions={countries}
          />
        )}
      </main>
    </div>
  );
}
