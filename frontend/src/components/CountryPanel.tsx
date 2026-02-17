import { useEffect, useState, useMemo } from 'react';
import {
  getCountryConflicts,
  getMetrics,
  getSpikes,
  getEvents,
  type CountryConflictsResponse,
  type Metric,
  type Spike,
  type EventItem,
} from '../api';

type PanelTab = 'context' | 'metrics' | 'spikes' | 'evidence';

interface CountryPanelProps {
  country: string;
  onClose: () => void;
}

function fetchWithTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error('Request timed out')), ms)),
  ]);
}

export default function CountryPanel({ country, onClose }: CountryPanelProps) {
  const [tab, setTab] = useState<PanelTab>('context');
  const [conflicts, setConflicts] = useState<CountryConflictsResponse | null>(null);
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [spikes, setSpikes] = useState<Spike[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [contextError, setContextError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setContextError(null);
    setConflicts(null);
    setMetrics([]);
    setSpikes([]);
    setEvents([]);

    // Fetch conflicts with timeout — won't block other data
    fetchWithTimeout(getCountryConflicts(country), 8000)
      .then((c) => { if (!cancelled) setConflicts(c); })
      .catch((e) => { if (!cancelled) setContextError(e instanceof Error ? e.message : 'Failed to load context'); });

    // Fetch remaining data independently
    Promise.allSettled([
      getMetrics({ country }),
      getSpikes({ country, limit: '100' }),
      getEvents({ country, limit: '100' }),
    ]).then((results) => {
      if (cancelled) return;
      if (results[0].status === 'fulfilled') setMetrics(results[0].value);
      if (results[1].status === 'fulfilled') setSpikes(results[1].value);
      if (results[2].status === 'fulfilled') setEvents(results[2].value);
      setLoading(false);
    });

    return () => { cancelled = true; };
  }, [country]);

  const riskOverTime = useMemo(() => {
    const byDate = new Map<string, { date: string; risk: number; events: number }>();
    for (const m of metrics) {
      const d = m.date;
      const cur = byDate.get(d);
      const risk = m.risk_score ?? 0;
      const ev = m.event_count ?? 0;
      if (!cur) byDate.set(d, { date: d, risk, events: ev });
      else byDate.set(d, { date: d, risk: Math.max(cur.risk, risk), events: cur.events + ev });
    }
    return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
  }, [metrics]);

  const tabs: { id: PanelTab; label: string }[] = [
    { id: 'context', label: 'Context' },
    { id: 'metrics', label: 'Metrics' },
    { id: 'spikes', label: 'Spikes' },
    { id: 'evidence', label: 'Evidence' },
  ];

  return (
    <div className="fixed inset-0 z-40 flex" onClick={onClose}>
      {/* Slide-in panel */}
      <div
        className="relative h-full w-[480px] max-w-[90vw] shrink-0 glass-heavy shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{ animation: 'slideInLeft 0.3s ease-out' }}
      >
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <h2 className="text-lg font-semibold text-slate-100">{country}</h2>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white/10 hover:text-slate-200"
              aria-label="Close"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-white/10 px-2">
            {tabs.map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={`px-3 py-2.5 text-sm font-medium transition ${
                  tab === id
                    ? 'border-b-2 border-cyan-400 text-cyan-400'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-5">
            {loading && (
              <div className="space-y-3">
                <div className="h-4 w-3/4 animate-pulse rounded bg-slate-700/50" />
                <div className="h-4 w-1/2 animate-pulse rounded bg-slate-700/50" />
                <div className="h-20 animate-pulse rounded bg-slate-700/50" />
              </div>
            )}

            {!loading && tab === 'context' && (
              <div className="space-y-4 text-sm">
                {contextError && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-900/20 px-3 py-2 text-amber-300 text-xs">
                    {contextError}
                  </div>
                )}
                {conflicts && (
                  <>
                    <section>
                      <h3 className="mb-1.5 font-medium text-slate-300">Current conflicts</h3>
                      <div className="whitespace-pre-wrap rounded-lg bg-white/5 p-3 text-slate-200 leading-relaxed">
                        {conflicts.current.conflicts}
                      </div>
                    </section>
                    <section>
                      <h3 className="mb-1.5 font-medium text-slate-300">Historical conflicts</h3>
                      <div className="whitespace-pre-wrap rounded-lg bg-white/5 p-3 text-slate-200 leading-relaxed">
                        {conflicts.past.conflicts}
                      </div>
                    </section>
                  </>
                )}
                {!conflicts && !contextError && (
                  <p className="text-slate-500">No conflict data available for this country.</p>
                )}
              </div>
            )}

            {!loading && tab === 'metrics' && (
              <div className="space-y-3">
                {riskOverTime.length > 0 ? (
                  <div>
                    <h3 className="mb-2 text-sm font-medium text-slate-400">Risk over time</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr className="border-b border-white/10 text-slate-400">
                            <th className="py-1.5 pr-2">Date</th>
                            <th className="py-1.5 pr-2">Risk</th>
                            <th className="py-1.5">Events</th>
                          </tr>
                        </thead>
                        <tbody>
                          {riskOverTime.slice(-14).reverse().map((r) => (
                            <tr key={r.date} className="border-b border-white/5 text-slate-300">
                              <td className="py-1.5 pr-2">{r.date}</td>
                              <td className="py-1.5 pr-2">{r.risk.toFixed(2)}</td>
                              <td className="py-1.5">{r.events}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-500">No metrics for this country</p>
                )}
              </div>
            )}

            {!loading && tab === 'spikes' && (
              <div>
                {spikes.length > 0 ? (
                  <ul className="space-y-2 text-sm">
                    {spikes.slice(0, 30).map((s) => (
                      <li key={s.id} className="flex justify-between rounded-lg bg-white/5 px-3 py-2 text-slate-300">
                        <span>{s.date} — {s.category}</span>
                        <span className="text-slate-400">z: {s.z_used != null ? s.z_used.toFixed(2) : s.z_score?.toFixed(2)}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-500">No spikes for this country</p>
                )}
              </div>
            )}

            {!loading && tab === 'evidence' && (
              <div>
                {events.length > 0 ? (
                  <ul className="space-y-2 text-sm">
                    {events.slice(0, 30).map((e) => (
                      <li key={e.id} className="rounded-lg bg-white/5 px-3 py-2 text-slate-300">
                        <span className="font-medium">{e.date}</span>
                        {e.category && <span className="ml-2 text-slate-400">{e.category}</span>}
                        {e.source_url && (
                          <a href={e.source_url} target="_blank" rel="noopener noreferrer" className="ml-2 text-cyan-400 hover:underline">
                            Source
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-slate-500">No events for this country</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Backdrop — click to close */}
      <div className="flex-1 bg-black/20" />

      <style>{`
        @keyframes slideInLeft {
          from { transform: translateX(-100%); }
          to { transform: translateX(0); }
        }
      `}</style>
    </div>
  );
}
