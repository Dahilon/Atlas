import type { MapCountryItem } from '../api';
import { useEventsStore } from '../stores/events-store';

interface SummaryStatsBarProps {
  countryData: MapCountryItem[];
}

export default function SummaryStatsBar({ countryData }: SummaryStatsBarProps) {
  const events = useEventsStore((s) => s.events);

  const totalEvents = events.length;
  const criticalCount = events.filter((e) => e.threatLevel === 'critical').length;
  const countriesMonitored = countryData.length;

  // Find top threat country
  const topCountry = countryData.length > 0
    ? countryData.reduce((a, b) => (a.severity_index ?? 0) > (b.severity_index ?? 0) ? a : b)
    : null;

  // Most common category
  const catCounts = new Map<string, number>();
  for (const e of events) {
    if (e.category) catCounts.set(e.category, (catCounts.get(e.category) ?? 0) + 1);
  }
  const topCategory = catCounts.size > 0
    ? [...catCounts.entries()].sort((a, b) => b[1] - a[1])[0][0]
    : null;

  return (
    <div className="fixed top-16 left-1/2 z-40 -translate-x-1/2">
      <div className="flex items-center gap-6 rounded-2xl glass px-5 py-2.5 shadow-lg">
        <Stat label="Events" value={totalEvents} />
        <div className="h-6 w-px bg-white/10" />
        <Stat label="Critical" value={criticalCount} color="red" />
        <div className="h-6 w-px bg-white/10" />
        <Stat label="Countries" value={countriesMonitored} />
        <div className="h-6 w-px bg-white/10" />
        <Stat label="Top Threat" value={topCountry?.country ?? '—'} />
        {topCategory && (
          <>
            <div className="h-6 w-px bg-white/10" />
            <Stat label="Trending" value={topCategory.split(' ')[0]} />
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="flex flex-col items-center">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={`text-sm font-bold ${color === 'red' ? 'text-red-400' : 'text-slate-100'}`}>
        {value}
      </span>
    </div>
  );
}
