/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_MAP_PROVIDER?: string;
  readonly VITE_MAP_TILE_URL?: string;
  readonly VITE_MAP_SUBDOMAINS?: string;
  readonly VITE_MAP_STYLE_URL?: string;
  readonly VITE_MAP_ATTRIBUTION?: string;
  readonly VITE_MAP_API_KEY?: string;
  readonly VITE_GEOCODING_PROVIDER?: string;
  readonly VITE_DEFAULT_MAP_CENTER_LAT?: string;
  readonly VITE_DEFAULT_MAP_CENTER_LON?: string;
  readonly VITE_DEFAULT_MAP_ZOOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

