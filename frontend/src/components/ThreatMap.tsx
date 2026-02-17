import { useMemo, useCallback, useState, useEffect } from 'react';
import Map, { Source, Layer, Popup, NavigationControl, ScaleControl } from 'react-map-gl/dist/maplibre.js';
import type { MapEvent, MilitaryBaseItem } from '../api';
import { useMapStore } from '../stores/map-store';
import { useEventsStore, applyFiltersToEvents } from '../stores/events-store';
import { getSeverityValue, threatLevelColors } from '../constants/colors';
import MapControls from './MapControls';
import EventPopup from './EventPopup';
import 'maplibre-gl/dist/maplibre-gl.css';

// Free MapLibre style (no token required)
const MAP_STYLE = 'https://demotiles.maplibre.org/style.json';

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
        severity: getSeverityValue(e.threatLevel),
        timestamp: e.timestamp,
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

interface ThreatMapProps {
  mapCountries?: Array<{ country: string; lat: number; lon: number; severity_index?: number | null; risk_score?: number | null }>;
  militaryBases?: MilitaryBaseItem[];
  onSelectCountry?: (country: string) => void;
}

export default function ThreatMap({
  militaryBases = [],
}: ThreatMapProps) {
  const { viewport, setViewport, showHeatmap, showClusters, showMilitaryBases, flyTo, flyToRequest, setFlyToRequest } = useMapStore();
  const events = useEventsStore((s) => s.events);
  const filters = useEventsStore((s) => s.filters);
  const selectedEvent = useEventsStore((s) => s.selectedEvent);
  const selectEvent = useEventsStore((s) => s.selectEvent);

  const filteredEvents = useMemo(() => applyFiltersToEvents(events, filters), [events, filters]);
  const eventsGeoJSON = useMemo(() => eventsToGeoJSON(filteredEvents), [filteredEvents]);
  const basesGeoJSON = useMemo(() => basesToGeoJSON(militaryBases), [militaryBases]);

  const [mapRef, setMapRef] = useState<unknown>(null);

  const onMapClick = useCallback(
    (evt: { features?: Array<{ properties?: { id?: string; cluster_id?: number }; layer?: { id: string } }>; lngLat: { lng: number; lat: number } }) => {
      const feats = evt.features;
      if (!feats?.length) {
        selectEvent(null);
        return;
      }
      const f = feats[0];
      const props = f.properties as { id?: string; cluster_id?: number } | undefined;
      if (f.layer?.id === 'unclustered-point' && props?.id) {
        const event = filteredEvents.find((e) => e.id === props.id);
        if (event) {
          selectEvent(event);
          flyTo(evt.lngLat.lng, evt.lngLat.lat, 8);
        }
      } else if (f.layer?.id === 'clusters' && mapRef && props?.cluster_id != null) {
        const clusterId = props.cluster_id;
        const map = mapRef as { getSource(id: string): { getClusterExpansionZoom?(id: number, cb: (err: Error | null, zoom: number) => void): void } | null; easeTo(options: { center: [number, number]; zoom: number }): void };
        const src = map.getSource('events');
        if (src?.getClusterExpansionZoom) {
          src.getClusterExpansionZoom(clusterId, (err: Error | null, zoom: number) => {
            if (!err && zoom != null && map.easeTo)
              map.easeTo({ center: [evt.lngLat.lng, evt.lngLat.lat], zoom: Math.min(zoom, 14) });
          });
        }
      }
    },
    [filteredEvents, selectEvent, flyTo, mapRef]
  );

  // Programmatic flyTo: when flyToRequest is set, tell the map to fly there (avoids controlled viewState loop)
  useEffect(() => {
    if (!flyToRequest || !mapRef) return;
    const map = mapRef as { flyTo(options: { center: [number, number]; zoom: number }): void };
    if (typeof map.flyTo === 'function') {
      map.flyTo({ center: [flyToRequest.longitude, flyToRequest.latitude], zoom: flyToRequest.zoom });
    }
    setFlyToRequest(null);
  }, [flyToRequest, mapRef, setFlyToRequest]);

  return (
    <div className="relative h-[70vh] w-full overflow-hidden rounded-xl border border-slate-700">
      <Map
        initialViewState={{
          longitude: viewport.longitude,
          latitude: viewport.latitude,
          zoom: viewport.zoom,
        }}
        onMove={(e: { viewState: typeof viewport }) => setViewport(e.viewState)}
        mapStyle={MAP_STYLE}
        onClick={onMapClick as (e: unknown) => void}
        onLoad={(e: { target: unknown }) => setMapRef(e.target)}
        interactiveLayerIds={['clusters', 'unclustered-point']}
      >
        <NavigationControl position="top-right" />
        <ScaleControl position="bottom-right" />

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
                  'step',
                  ['get', 'point_count'],
                  threatLevelColors.low,
                  10,
                  threatLevelColors.medium,
                  30,
                  threatLevelColors.high,
                  100,
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
              'circle-radius': 8,
            }}
          />
        </Source>

        {showHeatmap && (
          <Source id="events-heatmap" type="geojson" data={eventsGeoJSON}>
            <Layer
              id="heatmap"
              type="heatmap"
              paint={{
                'heatmap-weight': ['get', 'severity'],
                'heatmap-intensity': [
                  'interpolate',
                  ['linear'],
                  ['zoom'],
                  0, 0.5,
                  9, 1.5,
                ],
                'heatmap-color': [
                  'interpolate',
                  ['linear'],
                  ['heatmap-density'],
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

      <MapControls />
    </div>
  );
}
