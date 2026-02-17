import { useState } from 'react';
import EventFeed from './EventFeed';

interface SidebarProps {
  visible?: boolean;
}

export default function Sidebar({ visible = true }: SidebarProps) {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<'feed' | 'intel'>('feed');

  if (!visible) return null;

  // Collapsed state — small floating tab
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed right-3 top-20 z-30 rounded-xl glass px-2 py-3 text-slate-400 shadow-lg transition hover:text-slate-200"
        aria-label="Expand sidebar"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M10 4l-4 4 4 4" />
        </svg>
      </button>
    );
  }

  return (
    <div className="fixed right-4 top-20 bottom-4 z-30 flex w-[370px] flex-col rounded-2xl glass-heavy shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
        <div className="flex gap-1">
          <button
            type="button"
            onClick={() => setTab('feed')}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
              tab === 'feed' ? 'bg-cyan-600/80 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Event Feed
          </button>
          <button
            type="button"
            onClick={() => setTab('intel')}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition ${
              tab === 'intel' ? 'bg-cyan-600/80 text-white' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Intel
          </button>
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-lg p-1 text-slate-500 transition hover:bg-white/10 hover:text-slate-300"
          aria-label="Collapse sidebar"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 4l4 4-4 4" />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {tab === 'feed' && <EventFeed />}
        {tab === 'intel' && (
          <div className="p-4 text-sm text-slate-500">
            AI Search / Intel panel coming soon.
          </div>
        )}
      </div>
    </div>
  );
}
