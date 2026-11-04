import { apiRequest } from './api';

export interface GeocodedAddress {
  formatted_address: string;
  raw_display_name?: string;
  road?: string;
  suburb?: string;
  city?: string;
  postcode?: string;
  latitude: number;
  longitude: number;
}

export interface GeocodeResult {
  display_name: string;
  latitude: number;
  longitude: number;
  type?: string;
  importance?: number;
}

export interface PublicMapConfig {
  geocoding_enabled: boolean;
  geocoding_provider: string;
  default_center: {
    latitude: number;
    longitude: number;
  };
  default_zoom: number;
  supported_providers: string[];
  attribution_required: boolean;
}

export const mapService = {
  /**
   * Reverse-geocodes coordinates into a structured human-readable address
   * via backend proxy preserving citizen privacy.
   */
  async reverseGeocode(lat: number, lon: number): Promise<{ success: boolean; address: GeocodedAddress | null; error?: string }> {
    try {
      return await apiRequest(`/maps/reverse-geocode?lat=${lat}&lon=${lon}`);
    } catch (err: any) {
      return { success: false, address: null, error: err.message };
    }
  },

  /**
   * Forward searches coordinates by landmark or street query
   */
  async forwardGeocode(query: string, limit = 5): Promise<{ success: boolean; results: GeocodeResult[]; error?: string }> {
    try {
      return await apiRequest(`/maps/geocode?q=${encodeURIComponent(query)}&limit=${limit}`);
    } catch (err: any) {
      return { success: false, results: [], error: err.message };
    }
  },

  /**
   * Fetches backend map configuration parameters
   */
  async getPublicMapConfig(): Promise<PublicMapConfig> {
    return apiRequest<PublicMapConfig>('/maps/config');
  }
};

