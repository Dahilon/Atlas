import { useEffect, useState } from 'react';
import { getCountryInsights, type CountryInsights } from '../api';

type PanelTab = 'overview' | 'news' | 'metrics' | 'evidence';

interface CountryPanelProps {
  country: string;
  onClose: () => void;
}

const TIER_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  info: '#3b82f6',
  none: '#64748b',
};

const TREND_ICONS: Record<string, { arrow: string; color: string }> = {
  rising: { arrow: '▲', color: '#ef4444' },
  falling: { arrow: '▼', color: '#22c55e' },
  stable: { arrow: '●', color: '#94a3b8' },
};

export default function CountryPanel({ country, onClose }: CountryPanelProps) {
  const [tab, setTab] = useState<PanelTab>('overview');
  const [data, setData] = useState<CountryInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    setTab('overview');

    getCountryInsights(country)
      .then((d) => { if (!cancelled) setData(d); })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load insights'); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [country]);

  const tabs: { id: PanelTab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'news', label: 'News' },
    { id: 'metrics', label: 'Metrics' },
    { id: 'evidence', label: 'Evidence' },
  ];

  return (
    <div className="fixed inset-0 z-40 flex" onClick={onClose}>
      <div
        className="relative h-full w-[480px] max-w-[90vw] shrink-0 glass-heavy shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{ animation: 'slideInLeft 0.3s ease-out' }}
      >
        <div className="flex h-full flex-col">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-100">
                {data?.country_name || country}
              </h2>
              <span className="text-xs text-slate-500">{country}</span>
            </div>
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
                <div className="h-4 w-2/3 animate-pulse rounded bg-slate-700/50" />
              </div>
            )}

            {!loading && error && (
              <div className="rounded-lg border border-amber-500/30 bg-amber-900/20 px-3 py-2 text-amber-300 text-xs">
                {error}
              </div>
            )}

            {!loading && data && tab === 'overview' && (
              <OverviewTab data={data} />
            )}

            {!loading && data && tab === 'news' && (
              <NewsTab data={data} />
            )}

            {!loading && data && tab === 'metrics' && (
              <MetricsTab data={data} />
            )}

            {!loading && data && tab === 'evidence' && (
              <EvidenceTab data={data} />
            )}
          </div>
        </div>
      </div>

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

/* ── Overview Tab ── */
function OverviewTab({ data }: { data: CountryInsights }) {
  const { summary, risk_context, category_breakdown, related_countries } = data;
  const tierColor = TIER_COLORS[summary.risk_tier] ?? TIER_COLORS.none;
  const trend = TREND_ICONS[summary.trend] ?? TREND_ICONS.stable;

  return (
    <div className="space-y-4">
      {/* Risk Summary Card */}
      <div className="rounded-xl bg-white/5 p-4">
        <div className="flex items-center justify-between mb-3">
          <span
            className="rounded-full px-3 py-1 text-xs font-bold uppercase"
            style={{ backgroundColor: tierColor + '30', color: tierColor }}
          >
            {summary.risk_tier}
          </span>
          <span className="text-xs" style={{ color: trend.color }}>
            {trend.arrow} {summary.trend}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div>
            <div className="text-lg font-bold text-slate-100">{summary.severity.toFixed(1)}</div>
            <div className="text-[10px] uppercase text-slate-500">Severity</div>
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">{summary.event_count}</div>
            <div className="text-[10px] uppercase text-slate-500">Events</div>
          </div>
          <div>
            <div className="text-lg font-bold text-slate-100">
              {summary.avg_sentiment != null ? summary.avg_sentiment.toFixed(1) : '—'}
            </div>
            <div className="text-[10px] uppercase text-slate-500">Sentiment</div>
          </div>
        </div>
      </div>

      {/* Risk Context */}
      {risk_context && (
        <div className="text-sm leading-relaxed text-slate-300">{risk_context}</div>
      )}

      {/* Category Breakdown */}
      {Object.keys(category_breakdown).length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Categories</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(category_breakdown)
              .sort((a, b) => b[1] - a[1])
              .map(([cat, count]) => (
                <span key={cat} className="rounded-lg bg-white/5 px-2.5 py-1 text-xs text-slate-300">
                  {cat} <span className="text-slate-500">({count})</span>
                </span>
              ))}
          </div>
        </div>
      )}

      {/* Recent Events (top 5) */}
      {data.recent_events.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Recent Events</h3>
          <ul className="space-y-1.5">
            {data.recent_events.slice(0, 5).map((e) => (
              <li key={e.id} className="flex items-start gap-2 rounded-lg bg-white/5 px-3 py-2 text-xs">
                <span
                  className="mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: TIER_COLORS[e.threat_level] ?? '#64748b' }}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium text-slate-200">{e.title}</div>
                  <div className="flex items-center gap-2 text-slate-500">
                    <span>{e.date}</span>
                    {e.category && <span>{e.category}</span>}
                    {e.severity != null && <span>sev: {e.severity.toFixed(0)}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Related Countries */}
      {related_countries.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Related Countries</h3>
          <div className="flex flex-wrap gap-1.5">
            {related_countries.map((c) => (
              <span key={c} className="rounded bg-cyan-500/10 px-2 py-0.5 text-xs text-cyan-400">{c}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── News Tab ── */
function NewsTab({ data }: { data: CountryInsights }) {
  const { recent_news } = data;

  if (recent_news.length === 0) {
    return <p className="text-sm text-slate-500">No recent news available.</p>;
  }

  return (
    <div className="space-y-3">
      {recent_news.map((n, i) => (
        <div key={i} className="rounded-xl bg-white/5 p-3">
          <div className="mb-1.5 flex items-start gap-2">
            {n.threat_level && (
              <span
                className="mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
                style={{
                  backgroundColor: (TIER_COLORS[n.threat_level] ?? '#64748b') + '30',
                  color: TIER_COLORS[n.threat_level] ?? '#94a3b8',
                }}
              >
                {n.threat_level}
              </span>
            )}
            <div className="min-w-0 flex-1">
              {n.url ? (
                <a
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sm font-medium text-cyan-400 hover:underline leading-snug"
                >
                  {n.title}
                </a>
              ) : (
                <span className="text-sm font-medium text-slate-200">{n.title}</span>
              )}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
            {n.date && <span>{n.date}</span>}
            {n.source && <span>{n.source}</span>}
            {n.category && n.category !== 'Unknown' && (
              <span className="rounded bg-white/5 px-1.5 py-0.5">{n.category}</span>
            )}
            {n.confidence != null && (
              <span>conf: {(n.confidence * 100).toFixed(0)}%</span>
            )}
            {n.severity != null && n.severity > 0 && (
              <span>sev: {n.severity.toFixed(0)}</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── Metrics Tab ── */
function MetricsTab({ data }: { data: CountryInsights }) {
  const { metrics_history } = data;

  if (metrics_history.length === 0) {
    return <p className="text-sm text-slate-500">No metrics history available.</p>;
  }

  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Risk Over Time (14d)</h3>
      {/* Mini bar visualization */}
      <div className="mb-4 flex items-end gap-1 h-20">
        {metrics_history.map((m) => {
          const h = Math.max(4, (m.severity / 100) * 80);
          const color = m.severity >= 60 ? '#ef4444' : m.severity >= 40 ? '#eab308' : '#22c55e';
          return (
            <div key={m.date} className="flex-1 flex flex-col items-center gap-0.5" title={`${m.date}: ${m.severity.toFixed(1)}`}>
              <div className="w-full rounded-t" style={{ height: h, backgroundColor: color + '80' }} />
            </div>
          );
        })}
      </div>
      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 text-xs text-slate-500">
              <th className="py-1.5 pr-2">Date</th>
              <th className="py-1.5 pr-2">Severity</th>
              <th className="py-1.5">Events</th>
            </tr>
          </thead>
          <tbody>
            {[...metrics_history].reverse().map((m) => (
              <tr key={m.date} className="border-b border-white/5 text-slate-300">
                <td className="py-1.5 pr-2 text-xs">{m.date}</td>
                <td className="py-1.5 pr-2">{m.severity.toFixed(1)}</td>
                <td className="py-1.5">{m.events}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Evidence Tab ── */
function EvidenceTab({ data }: { data: CountryInsights }) {
  const { recent_events } = data;

  if (recent_events.length === 0) {
    return <p className="text-sm text-slate-500">No events found for this country.</p>;
  }

  return (
    <div>
      <div className="mb-2 text-xs text-slate-500">{recent_events.length} events (last 14 days)</div>
      <ul className="space-y-2">
        {recent_events.map((e) => (
          <li key={e.id} className="rounded-lg bg-white/5 px-3 py-2 text-sm">
            <div className="flex items-start gap-2">
              <span
                className="mt-1 inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: TIER_COLORS[e.threat_level] ?? '#64748b' }}
              />
              <div className="min-w-0 flex-1">
                <div className="font-medium text-slate-200">{e.title}</div>
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 mt-0.5">
                  <span>{e.date}</span>
                  {e.category && <span>{e.category}</span>}
                  {e.severity != null && <span>sev: {e.severity.toFixed(0)}</span>}
                  {e.sentiment != null && <span>tone: {e.sentiment.toFixed(1)}</span>}
                </div>
                {e.source_url && (
                  <a
                    href={e.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-xs text-cyan-400 hover:underline"
                  >
                    View source
                  </a>
                )}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
