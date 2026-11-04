import { describe, it, expect } from 'vitest';
import { 
  getMapConfig, 
  getFallbackTileConfig, 
  resolveTileConfig,
  validateCoordinates, 
  formatCoordinates,
  DEFAULT_MAP_TILE_URL,
  DEFAULT_MAP_SUBDOMAINS,
  DEFAULT_MAP_ATTRIBUTION,
  ESRI_DARK_GRAY_TILE_URL,
  MAP_PROVIDERS 
} from '../config/mapConfig';

describe('Map Provider Configuration & Portability', () => {
  it('should return valid default map configuration matching keyless Esri World Street Map', () => {
    const config = getMapConfig();
    expect(config).toBeDefined();
    expect(config.tileUrl).toBe(DEFAULT_MAP_TILE_URL);
    expect(config.tileUrl).toContain('server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}');
    expect(config.attribution).toContain('Esri');
    expect(config.defaultCenter).toHaveLength(2);
    expect(config.defaultZoom).toBeGreaterThan(0);
    expect(config.isConfigured).toBe(true);
  });

  it('should resolve keyless Esri tile config and protect against broken CARTO URLs', () => {
    const resolved = resolveTileConfig();
    expect(resolved.tileUrl).toBe(DEFAULT_MAP_TILE_URL);
    expect(resolved.subdomains).toEqual(['a', 'b', 'c', 'd']);
    expect(resolved.attribution).toContain('Esri');
    expect(resolved.tileUrl).not.toContain('cartocdn.com');
  });

  it('should support switching between providers including esri_dark and custom', () => {
    // Esri Streets
    const esri = MAP_PROVIDERS.esri_streets();
    expect(esri.provider).toBe('esri_streets');
    expect(esri.tileUrl).toBe(DEFAULT_MAP_TILE_URL);

    // Esri Dark Gray Canvas
    const esriDark = MAP_PROVIDERS.esri_dark();
    expect(esriDark.provider).toBe('esri_dark');
    expect(esriDark.tileUrl).toBe(ESRI_DARK_GRAY_TILE_URL);

    // Aliased carto/osm redirects safely to verified watermark-free Esri
    const carto = MAP_PROVIDERS.carto();
    expect(carto.tileUrl).toBe(DEFAULT_MAP_TILE_URL);

    // Custom municipal tile template
    const custom = MAP_PROVIDERS.custom(
      undefined, 
      'https://gis.city.gov/tiles/{z}/{x}/{y}.png',
      '&copy; City GIS Division'
    );
    expect(custom.provider).toBe('custom');
    expect(custom.tileUrl).toBe('https://gis.city.gov/tiles/{z}/{x}/{y}.png');
    expect(custom.attribution).toBe('&copy; City GIS Division');
  });

  it('should validate geographic coordinates correctly', () => {
    expect(validateCoordinates(17.4399, 78.4983)).toBe(true);
    expect(validateCoordinates(0, 0)).toBe(true);
    expect(validateCoordinates(-90, -180)).toBe(true);
    expect(validateCoordinates(90, 180)).toBe(true);

    // Invalid coordinates
    expect(validateCoordinates(91, 0)).toBe(false);
    expect(validateCoordinates(-91, 0)).toBe(false);
    expect(validateCoordinates(0, 181)).toBe(false);
    expect(validateCoordinates(0, -181)).toBe(false);
    expect(validateCoordinates(NaN, 50)).toBe(false);
    expect(validateCoordinates(50, NaN)).toBe(false);
  });

  it('should format coordinates to standard precision strings', () => {
    const formatted = formatCoordinates(17.43991234, 78.49835678, 4);
    expect(formatted).toBe('17.4399, 78.4984');

    const invalid = formatCoordinates(999, 999);
    expect(invalid).toBe('Invalid coordinates');
  });

  it('should supply a valid emergency fallback tile configuration', () => {
    const fallback = getFallbackTileConfig();
    expect(fallback.tileUrl).toBeDefined();
    expect(fallback.tileUrl).toContain('{z}/{y}/{x}');
    expect(fallback.attribution).toBeDefined();
  });
});
