/**
 * Mapbox token: read from window (set by public/env.js at runtime) or from process.env at build time.
 * Run `node scripts/write-env.js` (or `npm run env`) so frontend/.env is copied to public/env.js.
 */
declare global {
  interface Window {
    __MAPBOX_TOKEN__?: string;
  }
}
export const MAPBOX_TOKEN: string =
  (typeof window !== 'undefined' && window.__MAPBOX_TOKEN__) ||
  (typeof process !== 'undefined' && process.env && (process.env.VITE_MAPBOX_TOKEN || process.env.MAPBOX_TOKEN)) ||
  '';
