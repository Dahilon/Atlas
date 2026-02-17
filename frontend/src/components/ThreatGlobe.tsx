import { useMemo, useCallback, useRef, useEffect, useState } from 'react';
import Globe from 'react-globe.gl';
import type { MapEvent, MilitaryBaseItem } from '../api';
import { useMapStore } from '../stores/map-store';
import { useEventsStore, applyFiltersToEvents } from '../stores/events-store';
import { threatLevelColors } from '../constants/colors';
import MapControls from './MapControls';
import EventPopup from './EventPopup';

const BASE_COLOR = '#6366f1';
const GLOBE_BG = '#0f172a';
const EARTH_IMAGE = 'https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg';
const BUMP_IMAGE = 'https://unpkg.com/three-globe/example/img/earth-topology.png';

interface GlobePoint {
  lat: number;
  lng: number;
  color: string;
  label: string;
  type: 'event' | 'base';
  event?: MapEvent;
  base?: MilitaryBaseItem;
}

interface ThreatGlobeProps {
  militaryBases?: MilitaryBaseItem[];
}

export default function ThreatGlobe({ militaryBases = [] }: ThreatGlobeProps) {
  const globeRef = useRef<React.ElementRef<typeof Globe> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const { showMilitaryBases, flyTo } = useMapStore();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const { clientWidth, clientHeight } = el;
      if (clientWidth && clientHeight) setSize({ w: clientWidth, h: clientHeight });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const events = useEventsStore((s) => s.events);
  const filters = useEventsStore((s) => s.filters);
  const selectedEvent = useEventsStore((s) => s.selectedEvent);
  const selectEvent = useEventsStore((s) => s.selectEvent);

  const filteredEvents = useMemo(() => applyFiltersToEvents(events, filters), [events, filters]);

  const pointsData = useMemo((): GlobePoint[] => {
    const out: GlobePoint[] = [];
    filteredEvents.forEach((e) => {
      const lat = e.location?.latitude;
      const lng = e.location?.longitude;
      if (lat == null || lng == null) return;
      out.push({
        lat,
        lng,
        color: threatLevelColors[e.threatLevel] ?? threatLevelColors.info,
        label: e.title || e.id,
        type: 'event',
        event: e,
      });
    });
    if (showMilitaryBases) {
      militaryBases.forEach((b) => {
        out.push({
          lat: b.latitude,
          lng: b.longitude,
          color: BASE_COLOR,
          label: b.baseName || `${b.type} - ${b.country}`,
          type: 'base',
          base: b,
        });
      });
    }
    return out;
  }, [filteredEvents, showMilitaryBases, militaryBases]);

  const onGlobeReady = useCallback(() => {
    const ctrl = globeRef.current?.controls();
    if (ctrl) {
      (ctrl as { autoRotate?: boolean; autoRotateSpeed?: number }).autoRotate = true;
      (ctrl as { autoRotateSpeed?: number }).autoRotateSpeed = 0.4;
    }
  }, []);

  const onPointClick = useCallback(
    (point: GlobePoint) => {
      if (point.type === 'event' && point.event) {
        selectEvent(point.event);
        flyTo(point.lng, point.lat, 3);
      }
    },
    [selectEvent, flyTo]
  );

  // Programmatic flyTo: react-globe.gl uses pointOfView; we'd need to expose it via ref. For now we keep flyTo in store for sidebar; globe will just show selected event popup.
  return (
    <div ref={containerRef} className="relative h-[70vh] w-full overflow-hidden rounded-xl border border-slate-700">
      <Globe
        ref={globeRef}
        width={size.w}
        height={size.h}
        globeImageUrl={EARTH_IMAGE}
        bumpImageUrl={BUMP_IMAGE}
        backgroundColor={GLOBE_BG}
        showAtmosphere
        atmosphereColor="#1e293b"
        atmosphereAltitude={0.15}
        pointsData={pointsData}
        pointLat="lat"
        pointLng="lng"
        pointColor="color"
        pointLabel="label"
        pointAltitude={0.01}
        pointRadius={0.35}
        pointsMerge={false}
        onPointClick={onPointClick}
        onGlobeReady={onGlobeReady}
      />
      <MapControls />
      {selectedEvent && (
        <div
          className="absolute bottom-4 left-4 z-10 max-w-sm"
          style={{ pointerEvents: 'auto' }}
        >
          <EventPopup event={selectedEvent} />
          <button
            type="button"
            onClick={() => selectEvent(null)}
            className="mt-2 rounded bg-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-600"
          >
            Close
          </button>
        </div>
      )}
    </div>
  );
}
