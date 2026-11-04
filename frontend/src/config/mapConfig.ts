/**
 * CivicFix AI — Geospatial Configuration Layer
 * 
 * Basemap: Public Esri World Street Map Raster Tiles (HTTPS, Key-Free, High Availability)
 * Seamlessly replaces deprecated/watermarked CARTO endpoints with a verified,
 * keyless, watermark-free raster tile service.
 * 
 * URL Pattern: https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}
 * Attribution: Tiles &copy; Esri &mdash; see Esri's World Street Map attribution and usage terms
 */

export type MapProviderType = 
  | 'esri_streets' 
  | 'esri_dark' 
  | 'esri' 
  | 'carto_dark' 
  | 'carto_voyager' 
  | 'carto' 
  | 'osm' 
  | 'maptiler' 
  | 'custom';

export interface MapProviderConfig {
  provider: MapProviderType;
  name: string;
  tileUrl: string;
  styleUrl?: string;
  attribution: string;
  maxZoom: number;
  subdomains: string[];
  apiKey?: string;
  defaultCenter: [number, number];
  defaultZoom: number;
  geocodingProvider: 'backend' | 'nominatim' | 'disabled';
  isConfigured: boolean;
  configError?: string;
}

// Verified Public Key-Free Esri World Street Map Endpoint
export const DEFAULT_MAP_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}';
export const DEFAULT_MAP_SUBDOMAINS = ['a', 'b', 'c', 'd'];
export const DEFAULT_MAP_ATTRIBUTION = 'Tiles &copy; Esri &mdash; see Esri\'s World Street Map attribution and usage terms';

// Optional Dark Gray Canvas Layer (Key-Free)
export const ESRI_DARK_GRAY_TILE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
export const ESRI_DARK_GRAY_ATTRIBUTION = 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ';

const DEFAULT_CENTER: [number, number] = [
  Number(import.meta.env.VITE_DEFAULT_MAP_CENTER_LAT) || 17.4399,
  Number(import.meta.env.VITE_DEFAULT_MAP_CENTER_LON) || 78.4983,
];

const DEFAULT_ZOOM = Number(import.meta.env.VITE_DEFAULT_MAP_ZOOM) || 12;

const KNOWN_PLACEHOLDERS = new Set([
  'your_key',
  'your_api_key',
  'your_maptiler_api_key_here',
  'your_key_here',
  'placeholder',
  'none',
  'xxx',
  'changeme',
]);

/**
 * Resolves active basemap tile configuration from environment variables or defaults.
 * Protects runtime against watermarked/deprecated CARTO endpoints.
 */
export function resolveTileConfig() {
  const envUrl = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAP_TILE_URL : undefined;
  const isBrokenCarto = envUrl && typeof envUrl === 'string' && envUrl.includes('cartocdn.com');

  const tileUrl = (envUrl && typeof envUrl === 'string' && envUrl.trim().length > 0 && !isBrokenCarto)
    ? envUrl.trim()
    : DEFAULT_MAP_TILE_URL;

  const envSubdomains = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAP_SUBDOMAINS : undefined;
  const subdomains = envSubdomains
    ? String(envSubdomains).split(',').map((s) => s.trim())
    : DEFAULT_MAP_SUBDOMAINS;

  const envAttr = typeof import.meta !== 'undefined' ? import.meta.env?.VITE_MAP_ATTRIBUTION : undefined;
  const attribution = (envAttr && typeof envAttr === 'string' && envAttr.trim().length > 0 && !isBrokenCarto)
    ? envAttr.trim()
    : DEFAULT_MAP_ATTRIBUTION;

  return {
    tileUrl,
    subdomains,
    attribution,
    maxZoom: 19,
    providerName: 'Esri World Street Map (Key-Free)',
  };
}

export const MAP_PROVIDERS: Record<
  MapProviderType,
  (apiKey?: string, customTileUrl?: string, customAttr?: string) => Omit<MapProviderConfig, 'defaultCenter' | 'defaultZoom' | 'geocodingProvider'>
> = {
  esri_streets: () => ({
    provider: 'esri_streets',
    name: 'Esri World Street Map (Key-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  esri_dark: () => ({
    provider: 'esri_dark',
    name: 'Esri World Dark Gray Canvas (Key-Free)',
    tileUrl: ESRI_DARK_GRAY_TILE_URL,
    attribution: ESRI_DARK_GRAY_ATTRIBUTION,
    maxZoom: 16,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  esri: () => ({
    provider: 'esri',
    name: 'Esri World Street Map (Key-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  // Backward-compatibility aliases automatically redirect to verified key-free Esri basemap
  carto_dark: () => ({
    provider: 'carto_dark',
    name: 'Esri World Street Map (Watermark-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  carto_voyager: () => ({
    provider: 'carto_voyager',
    name: 'Esri World Street Map (Watermark-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  carto: () => ({
    provider: 'carto',
    name: 'Esri World Street Map (Watermark-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  osm: () => ({
    provider: 'osm',
    name: 'Esri World Street Map (Key-Free)',
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    maxZoom: 19,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
    isConfigured: true,
  }),
  maptiler: (apiKey) => {
    const rawKey = (apiKey !== undefined ? apiKey : (import.meta.env.VITE_MAP_API_KEY || '')).trim();
    const isUnsetOrPlaceholder = !rawKey || KNOWN_PLACEHOLDERS.has(rawKey.toLowerCase());

    if (isUnsetOrPlaceholder) {
      return {
        provider: 'maptiler',
        name: 'MapTiler Cloud (Fallback to Esri)',
        tileUrl: DEFAULT_MAP_TILE_URL,
        styleUrl: undefined,
        attribution: DEFAULT_MAP_ATTRIBUTION,
        maxZoom: 19,
        subdomains: DEFAULT_MAP_SUBDOMAINS,
        apiKey: '',
        isConfigured: true,
      };
    }

    return {
      provider: 'maptiler',
      name: 'MapTiler Cloud Streets',
      tileUrl: `https://api.maptiler.com/maps/streets-v2/256/{z}/{x}/{y}.png?key=${encodeURIComponent(rawKey)}`,
      styleUrl: `https://api.maptiler.com/maps/streets-v2/style.json?key=${encodeURIComponent(rawKey)}`,
      attribution: '&copy; <a href="https://www.maptiler.com/" target="_blank" rel="noopener noreferrer">MapTiler</a> &copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
      maxZoom: 20,
      subdomains: [],
      apiKey: rawKey,
      isConfigured: true,
    };
  },
  custom: (_apiKey, customTileUrl, customAttr) => {
    const tile = customTileUrl || import.meta.env.VITE_MAP_TILE_URL || '';
    if (!tile || tile.includes('cartocdn.com')) {
      return {
        provider: 'custom',
        name: 'Esri World Street Map (Safe Default)',
        tileUrl: DEFAULT_MAP_TILE_URL,
        styleUrl: undefined,
        attribution: DEFAULT_MAP_ATTRIBUTION,
        maxZoom: 19,
        subdomains: DEFAULT_MAP_SUBDOMAINS,
        isConfigured: true,
      };
    }
    return {
      provider: 'custom',
      name: 'Custom Municipal Basemap',
      tileUrl: tile,
      styleUrl: import.meta.env.VITE_MAP_STYLE_URL,
      attribution: customAttr || import.meta.env.VITE_MAP_ATTRIBUTION || DEFAULT_MAP_ATTRIBUTION,
      maxZoom: 20,
      subdomains: ['a', 'b', 'c', 'd'],
      isConfigured: true,
    };
  },
};

/**
 * Normalizes provider name alias
 */
function normalizeProvider(provider?: string): MapProviderType {
  const p = (provider || import.meta.env.VITE_MAP_PROVIDER || 'esri_streets').toLowerCase();
  if (p === 'esri' || p === 'esri_streets' || p === 'streets') return 'esri_streets';
  if (p === 'esri_dark' || p === 'dark_gray') return 'esri_dark';
  if (p === 'custom') return 'custom';
  // Aliases for previous names redirect safely to esri_streets
  if (p === 'carto' || p === 'dark' || p === 'carto_dark' || p === 'carto_voyager' || p === 'voyager' || p === 'osm') {
    return 'esri_streets';
  }
  return 'esri_streets';
}

/**
 * Returns the currently active, validated map configuration
 */
export function getMapConfig(providerOverride?: string): MapProviderConfig {
  const providerKey = normalizeProvider(providerOverride);
  const apiKey = import.meta.env.VITE_MAP_API_KEY || '';
  const customTile = import.meta.env.VITE_MAP_TILE_URL || '';
  const customAttr = import.meta.env.VITE_MAP_ATTRIBUTION || '';
  const geocoding = (import.meta.env.VITE_GEOCODING_PROVIDER || 'disabled') as 'backend' | 'nominatim' | 'disabled';

  const providerDetails = MAP_PROVIDERS[providerKey](apiKey, customTile, customAttr);

  return {
    ...providerDetails,
    defaultCenter: DEFAULT_CENTER,
    defaultZoom: DEFAULT_ZOOM,
    geocodingProvider: geocoding,
  };
}

/**
 * Key-free fallback tile configuration (Esri World Street Map)
 */
export function getFallbackTileConfig(): { tileUrl: string; attribution: string; subdomains: string[] } {
  return {
    tileUrl: DEFAULT_MAP_TILE_URL,
    attribution: DEFAULT_MAP_ATTRIBUTION,
    subdomains: DEFAULT_MAP_SUBDOMAINS,
  };
}

/**
 * Coordinate validator ensuring lat is [-90, 90] and lon is [-180, 180]
 */
export function validateCoordinates(lat: number, lon: number): boolean {
  if (typeof lat !== 'number' || typeof lon !== 'number') return false;
  if (isNaN(lat) || isNaN(lon)) return false;
  return lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

/**
 * Formats coordinates to standard decimal string representation
 */
export function formatCoordinates(lat: number, lon: number, precision = 5): string {
  if (!validateCoordinates(lat, lon)) return 'Invalid coordinates';
  return `${lat.toFixed(precision)}, ${lon.toFixed(precision)}`;
}
