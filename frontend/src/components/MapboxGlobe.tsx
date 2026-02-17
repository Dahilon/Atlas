import { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import Map, { Source, Layer, Popup, NavigationControl, ScaleControl } from 'react-map-gl/dist/mapbox.js';
import type { MapEvent, MapCountryItem, MilitaryBaseItem, ThreatLevel } from '../api';
import { useMapStore } from '../stores/map-store';
import { useEventsStore, applyFiltersToEvents } from '../stores/events-store';
import { getSeverityValue, threatLevelColors } from '../constants/colors';
import MapControls from './MapControls';
import MapLegend from './MapLegend';
import EventPopup from './EventPopup';
import 'mapbox-gl/dist/mapbox-gl.css';
import { MAPBOX_TOKEN } from '../config';

// ── Trend arrow symbols ──
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

// ── Risk tier → color mapping ──
const TIER_COLORS: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
  info: '#3b82f6',
};

function eventsToGeoJSON(events: MapEvent[]) {
  const features = events
    .filter((e) => e.location?.latitude != null && e.location?.longitude != null)
    .map((e) => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [e.location!.longitude, e.location!.latitude],
      },
      properties: {
        id: e.id,
        title: e.title,
        category: e.category,
        threatLevel: e.threatLevel,
        color: threatLevelColors[e.threatLevel] ?? threatLevelColors.info,
        severity: e.severity_index ?? getSeverityValue(e.threatLevel),
        timestamp: e.timestamp,
        confidence: e.category_confidence ?? null,
      },
    }));
  return { type: 'FeatureCollection' as const, features };
}

function countriesToGeoJSON(countries: MapCountryItem[]) {
  const features = countries
    .filter((c) => c.lat != null && c.lon != null)
    .map((c) => ({
      type: 'Feature' as const,
      geometry: {
        type: 'Point' as const,
        coordinates: [c.lon, c.lat],
      },
      properties: {
        country: c.country,
        severity: c.severity_index ?? 0,
        risk_tier: c.risk_tier ?? 'info',
        color: TIER_COLORS[c.risk_tier ?? 'info'] ?? TIER_COLORS.info,
        trend: c.trend_7d ?? 'stable',
        trend_arrow: TREND_ARROWS[c.trend_7d ?? 'stable'] ?? '●',
        trend_color: TREND_COLORS[c.trend_7d ?? 'stable'] ?? TREND_COLORS.stable,
        percentile: c.risk_percentile ?? 0,
        event_count: c.event_count ?? 0,
        top_category: c.top_category ?? '',
        label: `${c.country} ${TREND_ARROWS[c.trend_7d ?? 'stable'] ?? ''}`,
      },
    }));
  return { type: 'FeatureCollection' as const, features };
}

function basesToGeoJSON(bases: MilitaryBaseItem[]) {
  const features = bases.map((b) => ({
    type: 'Feature' as const,
    geometry: {
      type: 'Point' as const,
      coordinates: [b.longitude, b.latitude],
    },
    properties: { name: b.baseName, country: b.country, type: b.type },
  }));
  return { type: 'FeatureCollection' as const, features };
}

async function reverseGeocodeCountry(lng: number, lat: number, token: string): Promise<string | null> {
  const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${lng},${lat}.json?access_token=${encodeURIComponent(token)}&types=country`;
  const res = await fetch(url);
  if (!res.ok) return null;
  const data = (await res.json()) as { features?: Array<{ text?: string }> };
  return data.features?.[0]?.text ?? null;
}

interface MapboxGlobeProps {
  militaryBases?: MilitaryBaseItem[];
  countryData?: MapCountryItem[];
  onCountrySelect?: (country: string) => void;
  onClearAll?: () => void;
  className?: string;
}

const INITIAL_VIEW = { longitude: 0, latitude: 20, zoom: 2 };

export default function MapboxGlobe({ militaryBases = [], countryData = [], onCountrySelect, onClearAll, className }: MapboxGlobeProps) {
  const { showHeatmap, showClusters, showMilitaryBases, flyTo, flyToRequest, setFlyToRequest } = useMapStore();
  const events = useEventsStore((s) => s.events);
  const filters = useEventsStore((s) => s.filters);
  const selectedEvent = useEventsStore((s) => s.selectedEvent);
  const selectEvent = useEventsStore((s) => s.selectEvent);

  const filteredEvents = useMemo(() => applyFiltersToEvents(events, filters), [events, filters]);
  const eventsGeoJSON = useMemo(() => eventsToGeoJSON(filteredEvents), [filteredEvents]);
  const countriesGeoJSON = useMemo(() => countriesToGeoJSON(countryData), [countryData]);
  const basesGeoJSON = useMemo(() => basesToGeoJSON(militaryBases), [militaryBases]);

  const [mapRef, setMapRef] = useState<unknown>(null);
  const [hoveredCountry, setHoveredCountry] = useState<MapCountryItem | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  // ── Rotation with interaction pause ──
  const mapInstanceRef = useRef<unknown>(null);
  const isUserInteracting = useRef(false);
  const idleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleInteractionStart = useCallback(() => {
    isUserInteracting.current = true;
    if (idleTimerRef.current) {
      clearTimeout(idleTimerRef.current);
      idleTimerRef.current = null;
    }
  }, []);

  const handleInteractionEnd = useCallback(() => {
    if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    idleTimerRef.current = setTimeout(() => {
      isUserInteracting.current = false;
    }, 10000); // Resume after 10s idle
  }, []);

  const onMapClick = useCallback(
    async (evt: { features?: Array<{ properties?: Record<string, unknown>; layer?: { id: string } }>; lngLat: { lng: number; lat: number } }) => {
      const feats = evt.features;
      if (!feats?.length) {
        selectEvent(null);
        if (onCountrySelect && MAPBOX_TOKEN) {
          try {
            const country = await reverseGeocodeCountry(evt.lngLat.lng, evt.lngLat.lat, MAPBOX_TOKEN);
            if (country) onCountrySelect(country);
          } catch { /* ignore */ }
        }
        return;
      }
      const f = feats[0];
      const props = f.properties as Record<string, unknown>;
      if (f.layer?.id === 'country-risk-circles' && props?.country) {
        if (onCountrySelect) onCountrySelect(props.country as string);
        return;
      }
      if (f.layer?.id === 'unclustered-point' && props?.id) {
        const event = filteredEvents.find((e) => e.id === props.id);
        if (event) {
          selectEvent(event);
          flyTo(evt.lngLat.lng, evt.lngLat.lat, 8);
        }
      } else if (f.layer?.id === 'clusters' && mapRef && props?.cluster_id != null) {
        const map = mapRef as { getSource(id: string): { getClusterExpansionZoom?(id: number, cb: (err: Error | null, zoom: number) => void): void } | null; easeTo(options: { center: [number, number]; zoom: number }): void };
        const src = map.getSource('events');
        if (src?.getClusterExpansionZoom) {
          src.getClusterExpansionZoom(props.cluster_id as number, (err, zoom) => {
            if (!err && zoom != null)
              map.easeTo({ center: [evt.lngLat.lng, evt.lngLat.lat], zoom: Math.min(zoom, 14) });
          });
        }
      }
    },
    [filteredEvents, selectEvent, flyTo, mapRef, onCountrySelect]
  );

  // Hover handler for country risk circles
  const onMapMouseMove = useCallback(
    (evt: { features?: Array<{ properties?: Record<string, unknown> }>; point: { x: number; y: number } }) => {
      const feats = evt.features;
      if (feats?.length && feats[0].properties?.country) {
        const props = feats[0].properties;
        const match = countryData.find((c) => c.country === props.country);
        setHoveredCountry(match ?? null);
        setHoverPos({ x: evt.point.x, y: evt.point.y });
      } else {
        setHoveredCountry(null);
        setHoverPos(null);
      }
    },
    [countryData]
  );

  const onLoad = useCallback((e: { target: unknown }) => {
    const map = e.target as { setProjection?(name: string): void };
    if (typeof map.setProjection === 'function') map.setProjection('globe');
    setMapRef(e.target);
  }, []);

  // Auto-rotate (slow, pauses on interaction)
  useEffect(() => {
    if (!mapRef) return;
    mapInstanceRef.current = mapRef;
    let rafId: number;
    const tick = () => {
      if (!isUserInteracting.current) {
        const map = mapInstanceRef.current as { getBearing?: () => number; setBearing?: (b: number) => void } | null;
        if (map?.getBearing && map?.setBearing) map.setBearing(map.getBearing() + 0.008);
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(rafId);
      if (idleTimerRef.current) clearTimeout(idleTimerRef.current);
    };
  }, [mapRef]);

  // Fly-to requests
  useEffect(() => {
    if (!flyToRequest || !mapRef) return;
    const map = mapRef as { flyTo(options: { center: [number, number]; zoom: number }): void };
    if (typeof map.flyTo === 'function') {
      map.flyTo({ center: [flyToRequest.longitude, flyToRequest.latitude], zoom: flyToRequest.zoom });
    }
    setFlyToRequest(null);
  }, [flyToRequest, mapRef, setFlyToRequest]);

  if (!MAPBOX_TOKEN) {
    return (
      <div className={`flex items-center justify-center bg-slate-950 ${className ?? 'h-full w-full'}`}>
        <div className="text-center text-slate-400">
          <p className="font-medium">Mapbox token required</p>
          <p className="mt-1 text-sm">Set VITE_MAPBOX_TOKEN in .env for the 3D globe.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden ${className ?? 'h-full w-full'}`}>
      <Map
        mapboxAccessToken={MAPBOX_TOKEN}
        projection="globe"
        initialViewState={INITIAL_VIEW}
        style={{ width: '100%', height: '100%' }}
        mapStyle="mapbox://styles/mapbox/dark-v11"
        onClick={onMapClick as (e: unknown) => void}
        onMouseMove={onMapMouseMove as (e: unknown) => void}
        onMouseDown={handleInteractionStart}
        onMouseUp={handleInteractionEnd}
        onTouchStart={handleInteractionStart}
        onTouchEnd={handleInteractionEnd}
        onWheel={handleInteractionStart}
        onLoad={onLoad}
        interactiveLayerIds={['clusters', 'unclustered-point', 'country-risk-circles']}
      >
        <NavigationControl position="top-right" showCompass={false} />
        <ScaleControl position="bottom-right" />

        {/* ── Country risk circles (ML-derived tiers) ── */}
        {countriesGeoJSON.features.length > 0 && (
          <Source id="country-risk" type="geojson" data={countriesGeoJSON}>
            <Layer
              id="country-risk-circles"
              type="circle"
              paint={{
                'circle-color': ['get', 'color'],
                'circle-radius': [
                  'interpolate', ['linear'], ['get', 'severity'],
                  0, 8,
                  50, 14,
                  100, 22,
                ],
                'circle-opacity': 0.75,
                'circle-stroke-width': 2,
                'circle-stroke-color': '#ffffff',
                'circle-stroke-opacity': 0.4,
              }}
            />
            <Layer
              id="country-labels"
              type="symbol"
              layout={{
                'text-field': ['get', 'label'],
                'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
                'text-size': 11,
                'text-offset': [0, -2],
                'text-allow-overlap': false,
              }}
              paint={{
                'text-color': '#e2e8f0',
                'text-halo-color': '#0f172a',
                'text-halo-width': 1.5,
              }}
            />
          </Source>
        )}

        {/* ── Event markers ── */}
        <Source
          id="events"
          type="geojson"
          data={eventsGeoJSON}
          cluster={showClusters}
          clusterMaxZoom={14}
          clusterRadius={50}
        >
          {showClusters && (
            <Layer
              id="clusters"
              type="circle"
              filter={['has', 'point_count']}
              paint={{
                'circle-color': [
                  'step', ['get', 'point_count'],
                  threatLevelColors.low, 10,
                  threatLevelColors.medium, 30,
                  threatLevelColors.high, 100,
                  threatLevelColors.critical,
                ],
                'circle-radius': ['step', ['get', 'point_count'], 12, 10, 16, 30, 20, 100, 24],
              }}
            />
          )}
          {showClusters && (
            <Layer
              id="cluster-count"
              type="symbol"
              filter={['has', 'point_count']}
              layout={{
                'text-field': ['get', 'point_count_abbreviated'],
                'text-font': ['DIN Offc Pro Medium', 'Arial Unicode MS Bold'],
                'text-size': 12,
              }}
              paint={{ 'text-color': '#fff' }}
            />
          )}
          <Layer
            id="unclustered-point"
            type="circle"
            filter={showClusters ? ['!', ['has', 'point_count']] : ['boolean', true]}
            paint={{
              'circle-color': ['get', 'color'],
              'circle-radius': 6,
              'circle-opacity': 0.8,
            }}
          />
        </Source>

        {/* ── Heatmap ── */}
        {showHeatmap && (
          <Source id="events-heatmap" type="geojson" data={eventsGeoJSON}>
            <Layer
              id="heatmap"
              type="heatmap"
              paint={{
                'heatmap-weight': ['interpolate', ['linear'], ['get', 'severity'], 0, 0, 100, 1],
                'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 0.5, 9, 1.5],
                'heatmap-color': [
                  'interpolate', ['linear'], ['heatmap-density'],
                  0, 'rgba(59, 130, 246, 0)',
                  0.3, 'rgba(59, 130, 246, 0.5)',
                  0.6, 'rgba(234, 179, 8, 0.7)',
                  0.9, 'rgba(249, 115, 22, 0.8)',
                  1, 'rgba(239, 68, 68, 0.9)',
                ],
                'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 8, 9, 20],
              }}
            />
          </Source>
        )}

        {/* ── Military bases ── */}
        {showMilitaryBases && basesGeoJSON.features.length > 0 && (
          <Source id="military-bases" type="geojson" data={basesGeoJSON}>
            <Layer
              id="bases-layer"
              type="circle"
              paint={{
                'circle-color': '#6366f1',
                'circle-radius': 6,
                'circle-stroke-width': 2,
                'circle-stroke-color': '#fff',
              }}
            />
          </Source>
        )}

        {/* ── Selected event popup ── */}
        {selectedEvent && (
          <Popup
            longitude={selectedEvent.location?.longitude ?? 0}
            latitude={selectedEvent.location?.latitude ?? 0}
            onClose={() => selectEvent(null)}
            closeButton
            closeOnClick={false}
            anchor="bottom"
          >
            <EventPopup event={selectedEvent} />
          </Popup>
        )}
      </Map>

      {/* ── Hover tooltip for country risk ── */}
      {hoveredCountry && hoverPos && (
        <div
          className="pointer-events-none absolute z-50 glass-heavy rounded-lg px-3 py-2 text-sm shadow-xl"
          style={{ left: hoverPos.x + 12, top: hoverPos.y - 40 }}
        >
          <div className="flex items-center gap-2">
            <span className="text-base font-bold text-slate-100">{hoveredCountry.country}</span>
            <span
              className="rounded px-1.5 py-0.5 text-xs font-semibold uppercase"
              style={{
                backgroundColor: TIER_COLORS[hoveredCountry.risk_tier ?? 'info'] + '30',
                color: TIER_COLORS[hoveredCountry.risk_tier ?? 'info'],
              }}
            >
              {hoveredCountry.risk_tier ?? 'info'}
            </span>
            {hoveredCountry.trend_7d && (
              <span style={{ color: TREND_COLORS[hoveredCountry.trend_7d] }}>
                {TREND_ARROWS[hoveredCountry.trend_7d]}
              </span>
            )}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Severity: <span className="text-slate-200">{hoveredCountry.severity_index?.toFixed(1) ?? '—'}</span>
            {' · '}
            Percentile: <span className="text-slate-200">{hoveredCountry.risk_percentile?.toFixed(0) ?? '—'}th</span>
            {' · '}
            Events: <span className="text-slate-200">{hoveredCountry.event_count ?? 0}</span>
          </div>
          {hoveredCountry.top_category && (
            <div className="mt-0.5 text-xs text-slate-500">
              Top: {hoveredCountry.top_category}
            </div>
          )}
        </div>
      )}

      <MapControls onClearAll={onClearAll} />
      <MapLegend />
    </div>
  );
}
