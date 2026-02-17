import { useMapStore } from '../stores/map-store';
import { useEventsStore } from '../stores/events-store';

interface MapControlsProps {
  onClearAll?: () => void;
}

export default function MapControls({ onClearAll }: MapControlsProps) {
  const {
    showHeatmap,
    showClusters,
    showMilitaryBases,
    setShowHeatmap,
    setShowClusters,
    setShowMilitaryBases,
    resetMapState,
  } = useMapStore();

  const clearFilters = useEventsStore((s) => s.clearFilters);
  const selectEvent = useEventsStore((s) => s.selectEvent);

  const handleClearAll = () => {
    resetMapState();
    clearFilters();
    selectEvent(null);
    onClearAll?.();
  };

  return (
    <div className="absolute right-14 top-14 z-10 flex flex-col gap-2 rounded-xl glass px-3 py-2.5 shadow-lg">
      <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          checked={showClusters}
          onChange={(e) => setShowClusters(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-500 bg-slate-700 accent-cyan-500"
        />
        Clusters
      </label>
      <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          checked={showHeatmap}
          onChange={(e) => setShowHeatmap(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-500 bg-slate-700 accent-cyan-500"
        />
        Heatmap
      </label>
      <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
        <input
          type="checkbox"
          checked={showMilitaryBases}
          onChange={(e) => setShowMilitaryBases(e.target.checked)}
          className="h-3.5 w-3.5 rounded border-slate-500 bg-slate-700 accent-cyan-500"
        />
        Bases
      </label>
      <div className="my-0.5 border-t border-white/10" />
      <button
        type="button"
        onClick={handleClearAll}
        className="rounded-lg bg-slate-700/50 px-2 py-1 text-xs text-slate-400 transition hover:bg-red-900/40 hover:text-red-300"
      >
        Clear All
      </button>
    </div>
  );
}
