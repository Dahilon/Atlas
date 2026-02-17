/** Dynamic map legend showing risk tier colors and trend arrows. */
export default function MapLegend() {
  const tiers = [
    { label: 'Critical', color: '#ef4444' },
    { label: 'High', color: '#f97316' },
    { label: 'Medium', color: '#eab308' },
    { label: 'Low', color: '#22c55e' },
    { label: 'Info', color: '#3b82f6' },
  ];

  const trends = [
    { label: 'Rising', symbol: '▲', color: '#ef4444' },
    { label: 'Stable', symbol: '●', color: '#94a3b8' },
    { label: 'Falling', symbol: '▼', color: '#22c55e' },
  ];

  return (
    <div className="absolute bottom-4 left-4 z-40 rounded-xl glass px-3 py-2 text-xs">
      <div className="mb-1 font-semibold text-slate-300">Risk Tiers (ML)</div>
      <div className="flex gap-2.5">
        {tiers.map((t) => (
          <div key={t.label} className="flex items-center gap-1">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: t.color }}
            />
            <span className="text-slate-400">{t.label}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 flex gap-2.5">
        {trends.map((t) => (
          <div key={t.label} className="flex items-center gap-1">
            <span className="text-[10px]" style={{ color: t.color }}>{t.symbol}</span>
            <span className="text-slate-400">{t.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
