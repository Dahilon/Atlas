import { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  LineChart, Line,
} from 'recharts';
import {
  getRiskDistribution, getRiskTiers, getCategoryBreakdown, getTopMovers, getSparklines,
  type RiskDistribution, type RiskTiers, type CategoryBreakdown, type TopMover, type SparklineData,
} from '../api';

const TIER_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  info: '#3b82f6',
};

const CATEGORY_COLORS = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#3b82f6', '#8b5cf6'];

const TREND_ARROWS: Record<string, string> = {
  rising: '▲',
  falling: '▼',
  stable: '●',
};

const TREND_COLORS: Record<string, string> = {
  rising: '#ef4444',
  falling: '#22c55e',
  stable: '#94a3b8',
};

const BIN_COLORS: Record<string, string> = {
  '0-20': '#3b82f6',
  '20-40': '#22c55e',
  '40-60': '#eab308',
  '60-80': '#f97316',
  '80-100': '#ef4444',
};

interface AnalyticsViewProps {
  onClose?: () => void;
}

export default function AnalyticsView({ onClose }: AnalyticsViewProps) {
  const [dist, setDist] = useState<RiskDistribution | null>(null);
  const [tiers, setTiers] = useState<RiskTiers | null>(null);
  const [categories, setCategories] = useState<CategoryBreakdown | null>(null);
  const [movers, setMovers] = useState<TopMover[]>([]);
  const [sparklines, setSparklines] = useState<SparklineData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getRiskDistribution(),
      getRiskTiers(),
      getCategoryBreakdown(7),
      getTopMovers(15),
    ]).then(([d, t, c, m]) => {
      if (cancelled) return;
      setDist(d);
      setTiers(t);
      setCategories(c);
      setMovers(m);
      const topCountries = m.slice(0, 5).map((x) => x.country);
      if (topCountries.length > 0) {
        getSparklines(topCountries).then((s) => { if (!cancelled) setSparklines(s); });
      }
    }).catch(() => {})
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="fixed inset-0 z-20 overflow-y-auto pt-20 pb-8 px-4 sm:px-6">
      {/* Semi-transparent backdrop */}
      <div className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={onClose} />

      {/* Content */}
      <div className="relative z-10 mx-auto max-w-6xl space-y-5">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-100">Analytics Dashboard</h2>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl glass px-3 py-1.5 text-sm text-slate-400 transition hover:text-slate-200"
            >
              Back to Map
            </button>
          )}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-20">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
          </div>
        )}

        {!loading && (
          <>
            {/* Row 1: Distribution + Categories */}
            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              {/* Risk Distribution Histogram */}
              <div className="rounded-2xl glass-heavy p-5">
                <h3 className="mb-3 text-sm font-semibold text-slate-300">Severity Distribution</h3>
                {dist && (
                  <>
                    <ResponsiveContainer width="100%" height={200}>
                      <BarChart data={dist.bins}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                        <XAxis dataKey="range" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                        <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
                          labelStyle={{ color: '#e2e8f0' }}
                          itemStyle={{ color: '#94a3b8' }}
                        />
                        <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                          {dist.bins.map((entry) => (
                            <Cell key={entry.range} fill={BIN_COLORS[entry.range] ?? '#64748b'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-slate-400">
                      <span>Mean: <span className="text-slate-200">{dist.stats.mean}</span></span>
                      <span>Median: <span className="text-slate-200">{dist.stats.median}</span></span>
                      <span>Std: <span className="text-slate-200">{dist.stats.std}</span></span>
                      <span>n={dist.stats.count}</span>
                    </div>
                  </>
                )}
              </div>

              {/* Category Breakdown */}
              <div className="rounded-2xl glass-heavy p-5">
                <h3 className="mb-3 text-sm font-semibold text-slate-300">Category Breakdown (7d)</h3>
                {categories && (
                  <>
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={categories.categories}
                          dataKey="count"
                          nameKey="name"
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={80}
                          paddingAngle={2}
                          label={({ name, percentage }) => `${name?.split(' ')[0]} ${percentage}%`}
                          labelLine={false}
                        >
                          {categories.categories.map((_, i) => (
                            <Cell key={i} fill={CATEGORY_COLORS[i % CATEGORY_COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #475569', borderRadius: 8 }}
                          itemStyle={{ color: '#e2e8f0' }}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="mt-1 text-center text-xs text-slate-500">
                      Total: {categories.total} events
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Row 2: Risk Tier Boundaries */}
            {tiers && tiers.boundaries.length > 0 && (
              <div className="rounded-2xl glass-heavy p-5">
                <h3 className="mb-3 text-sm font-semibold text-slate-300">
                  Risk Tier Boundaries ({tiers.method.toUpperCase()} · n={tiers.n_samples})
                </h3>
                <div className="flex items-center gap-1">
                  {Object.entries(tiers.tier_ranges).map(([tier, [low, high]]) => {
                    const width = ((high - low) / 100) * 100;
                    return (
                      <div
                        key={tier}
                        className="relative flex flex-col items-center justify-center rounded-lg py-2 text-center text-xs font-medium"
                        style={{
                          width: `${Math.max(width, 10)}%`,
                          backgroundColor: (TIER_COLORS[tier] ?? '#64748b') + '40',
                          color: TIER_COLORS[tier] ?? '#94a3b8',
                        }}
                      >
                        <span className="font-semibold capitalize">{tier}</span>
                        <span className="text-[10px] opacity-70">{low.toFixed(0)}–{high.toFixed(0)}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Row 3: Top Movers Table */}
            <div className="rounded-2xl glass-heavy p-5">
              <h3 className="mb-3 text-sm font-semibold text-slate-300">Top Risk Movers</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase text-slate-500">
                      <th className="py-2 pr-4">Country</th>
                      <th className="py-2 pr-4">Severity</th>
                      <th className="py-2 pr-4">Tier</th>
                      <th className="py-2 pr-4">Percentile</th>
                      <th className="py-2 pr-4">Trend</th>
                      <th className="py-2 pr-4">Events</th>
                      <th className="py-2">Sparkline</th>
                    </tr>
                  </thead>
                  <tbody>
                    {movers.map((m) => {
                      const spark = sparklines.find((s) => s.country === m.country);
                      return (
                        <tr key={m.country} className="border-b border-white/5 hover:bg-white/5">
                          <td className="py-2 pr-4 font-medium text-slate-200">{m.country}</td>
                          <td className="py-2 pr-4 text-slate-300">{m.severity_index?.toFixed(1) ?? '—'}</td>
                          <td className="py-2 pr-4">
                            <span
                              className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase"
                              style={{
                                backgroundColor: (TIER_COLORS[m.risk_tier ?? 'info'] ?? '#64748b') + '30',
                                color: TIER_COLORS[m.risk_tier ?? 'info'] ?? '#94a3b8',
                              }}
                            >
                              {m.risk_tier ?? '—'}
                            </span>
                          </td>
                          <td className="py-2 pr-4 text-slate-400">{m.risk_percentile?.toFixed(0) ?? '—'}th</td>
                          <td className="py-2 pr-4">
                            {m.trend_7d ? (
                              <span style={{ color: TREND_COLORS[m.trend_7d] }}>
                                {TREND_ARROWS[m.trend_7d]} {m.trend_7d}
                              </span>
                            ) : (
                              <span className="text-slate-500">—</span>
                            )}
                          </td>
                          <td className="py-2 pr-4 text-slate-400">{m.event_count}</td>
                          <td className="py-2">
                            {spark && spark.values.length > 1 ? (
                              <div className="h-6 w-24">
                                <ResponsiveContainer width="100%" height="100%">
                                  <LineChart data={spark.values.map((v, i) => ({ v, i }))}>
                                    <Line
                                      type="monotone"
                                      dataKey="v"
                                      stroke={TIER_COLORS[m.risk_tier ?? 'info'] ?? '#64748b'}
                                      strokeWidth={1.5}
                                      dot={false}
                                    />
                                  </LineChart>
                                </ResponsiveContainer>
                              </div>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Row 4: Data Science Methods */}
            <div className="rounded-2xl glass-heavy p-5">
              <h3 className="mb-3 text-sm font-semibold text-slate-300">Data Science Methods</h3>
              <div className="grid grid-cols-1 gap-3 text-xs text-slate-400 sm:grid-cols-2 lg:grid-cols-3">
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">NLP Classification</div>
                  <p>TF-IDF + Logistic Regression trained on labeled event data. 6 categories with probability distribution and confidence scores.</p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">Severity Scoring</div>
                  <p>Composite index (0-100): 30% sentiment, 25% keyword intensity, 20% category weight, 15% entity density, 10% recency.</p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">Risk Tier Classification</div>
                  <p>Jenks Natural Breaks optimization on severity distribution. Adaptive boundaries recomputed with each pipeline run.</p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">Trend Detection</div>
                  <p>Linear regression + Mann-Kendall non-parametric test. Classifies countries as rising/stable/falling with R² confidence.</p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">Entity Extraction</div>
                  <p>spaCy NER extracts countries, organizations, and persons. pycountry resolves entities to ISO-2 codes.</p>
                </div>
                <div className="rounded-xl bg-white/5 p-3">
                  <div className="mb-1 font-semibold text-cyan-400">Anomaly Detection</div>
                  <p>Ensemble: IQR outliers + Isolation Forest (multi-variate) + CUSUM drift detection. Requires 2-of-3 agreement.</p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
