import { create } from 'zustand';

export interface ViewportState {
  longitude: number;
  latitude: number;
  zoom: number;
  bearing?: number;
  pitch?: number;
  padding?: { top?: number; bottom?: number; left?: number; right?: number };
}

const defaultViewport: ViewportState = {
  longitude: 0,
  latitude: 20,
  zoom: 2,
};

export interface FlyToRequest {
  longitude: number;
  latitude: number;
  zoom: number;
}

interface MapStore {
  viewport: ViewportState;
  setViewport: (v: Partial<ViewportState>) => void;
  flyToRequest: FlyToRequest | null;
  setFlyToRequest: (r: FlyToRequest | null) => void;
  showHeatmap: boolean;
  showClusters: boolean;
  showMilitaryBases: boolean;
  setShowHeatmap: (v: boolean) => void;
  setShowClusters: (v: boolean) => void;
  setShowMilitaryBases: (v: boolean) => void;
  selectedCountryCode: string | null;
  setSelectedCountryCode: (code: string | null) => void;
  flyTo: (lon: number, lat: number, zoom?: number) => void;
}

export const useMapStore = create<MapStore>((set) => ({
  viewport: defaultViewport,
  setViewport: (v) =>
    set((s) => ({
      viewport: { ...s.viewport, ...v },
    })),
  flyToRequest: null,
  setFlyToRequest: (r) => set({ flyToRequest: r }),
  showHeatmap: false,
  showClusters: true,
  showMilitaryBases: false,
  setShowHeatmap: (v) => set({ showHeatmap: v }),
  setShowClusters: (v) => set({ showClusters: v }),
  setShowMilitaryBases: (v) => set({ showMilitaryBases: v }),
  selectedCountryCode: null,
  setSelectedCountryCode: (code) => set({ selectedCountryCode: code }),
  flyTo: (longitude, latitude, zoom = 6) =>
    set({ flyToRequest: { longitude, latitude, zoom } }),
}));
