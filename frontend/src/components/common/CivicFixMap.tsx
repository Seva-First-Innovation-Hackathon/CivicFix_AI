import React, { useEffect, useState, Component, type ReactNode, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap, useMapEvents } from 'react-leaflet';
import L from 'leaflet';
import { useNavigate } from 'react-router-dom';
import { 
  MapPin, Navigation, AlertCircle, RefreshCw, 
  Compass, CheckCircle2, Loader2, ExternalLink 
} from 'lucide-react';

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

import { 
  getMapConfig, 
  resolveTileConfig,
  validateCoordinates, 
  formatCoordinates, 
  MapProviderType 
} from '../../config/mapConfig';

// Fix Leaflet default marker icon paths in Vite bundling
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

// Data item interface for viewer mode
export interface MapComplaintItem {
  id: string;
  reference_number: string;
  title: string;
  category: string;
  status: string;
  priority: string;
  latitude: number;
  longitude: number;
  address?: string;
  first_image?: string;
}

// Data item interface for crew mode
export interface MapWorkOrderItem {
  id: string;
  complaint_id: string;
  complaint_reference?: string;
  title: string;
  status: string;
  instructions?: string;
  complaint_address?: string;
  complaint_latitude?: number;
  complaint_longitude?: number;
}

export interface CivicFixMapProps {
  mode?: 'picker' | 'viewer' | 'crew';
  center?: [number, number];
  zoom?: number;
  height?: string;
  // Picker props
  latitude?: number;
  longitude?: number;
  onLocationChange?: (lat: number, lon: number, addressSuggestion?: string) => void;
  disabled?: boolean;
  // Viewer props
  complaints?: MapComplaintItem[];
  onSelectComplaint?: (id: string) => void;
  // Crew props
  workOrders?: MapWorkOrderItem[];
  onSelectWorkOrder?: (id: string) => void;
  // Tile override
  providerOverride?: MapProviderType;
}

/**
 * RouteWise AI-style Error Boundary ensuring map rendering issues
 * never crash the surrounding application.
 */
class MapErrorBoundary extends Component<{ children: ReactNode; fallbackHeight?: string }, { hasError: boolean }> {
  constructor(props: { children: ReactNode; fallbackHeight?: string }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: any) {
    console.warn('[CivicFix MapErrorBoundary caught]', error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="rounded-2xl border border-slate-700 bg-slate-900/95 p-6 flex flex-col items-center justify-center text-center space-y-2 text-xs text-slate-300"
          style={{ height: this.props.fallbackHeight || '320px' }}
        >
          <span className="text-amber-400 font-bold text-sm">Interactive Map Fallback</span>
          <p className="max-w-md text-slate-400">
            Interactive map tiles temporarily unavailable. Geographic incident coordinates remain safely stored in the database.
          </p>
          <button
            onClick={() => this.setState({ hasError: false })}
            className="mt-3 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-white rounded-lg text-xs font-semibold"
          >
            Reload Map Component
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * RouteWise AI multi-pass size invalidator to prevent grey/blank tiles
 * when the map renders in tabs, modals, or animated flex/grid layouts.
 */
function InvalidateMapSize() {
  const map = useMap();
  useEffect(() => {
    map.invalidateSize();
    const t1 = setTimeout(() => {
      try {
        map.invalidateSize();
      } catch {}
    }, 120);

    const t2 = setTimeout(() => {
      try {
        map.invalidateSize();
      } catch {}
    }, 350);

    let ro: ResizeObserver | null = null;
    const container = map.getContainer();
    if (container && typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => {
        try {
          map.invalidateSize();
        } catch {}
      });
      ro.observe(container);
    }

    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      if (ro) ro.disconnect();
    };
  }, [map]);

  return null;
}

/**
 * Handles map click events to select coordinates in picker mode.
 * Strictly keyless & local: No Nominatim or third-party geocoding calls made.
 */
function LocationPickerHandler({
  onLocationChange,
  disabled,
}: {
  onLocationChange?: (lat: number, lon: number) => void;
  disabled?: boolean;
}) {
  useMapEvents({
    click(e) {
      if (disabled || !onLocationChange) return;
      const cleanLat = Number(e.latlng.lat.toFixed(5));
      const cleanLon = Number(e.latlng.lng.toFixed(5));
      onLocationChange(cleanLat, cleanLon);
    },
  });
  return null;
}

/**
 * Smoothly updates center view when coordinates change from GPS or manual input.
 */
function MapCenterUpdater({
  target,
  zoom,
}: {
  target: [number, number];
  zoom?: number;
}) {
  const map = useMap();
  useEffect(() => {
    if (validateCoordinates(target[0], target[1])) {
      map.setView(target, zoom || map.getZoom(), { animate: true });
    }
  }, [target[0], target[1], zoom, map]);
  return null;
}

/**
 * Fits bounds automatically around multiple markers in viewer or crew mode.
 */
function FitBoundsUpdater({
  points,
}: {
  points: [number, number][];
}) {
  const map = useMap();
  useEffect(() => {
    if (points.length >= 2) {
      try {
        const bounds = L.latLngBounds(points);
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [40, 40], maxZoom: 15 });
        }
      } catch (err) {
        console.warn('[FitBoundsUpdater caught]', err);
      }
    } else if (points.length === 1 && validateCoordinates(points[0][0], points[0][1])) {
      map.setView(points[0], 14, { animate: true });
    }
  }, [points, map]);
  return null;
}

/**
 * Creates accessible SVG icons with distinct geometric glyphs
 * so priority is never communicated by color alone.
 */
function createCivicMarkerIcon(priority: string, status: string, isCrew = false): L.DivIcon {
  let bg = '#3b82f6';
  let glyph = '●';

  if (status === 'RESOLVED') {
    bg = '#10b981';
    glyph = '✓';
  } else if (priority === 'P1') {
    bg = '#ef4444';
    glyph = '▲';
  } else if (priority === 'P2') {
    bg = '#f97316';
    glyph = '◆';
  } else if (priority === 'P4') {
    bg = '#64748b';
    glyph = '■';
  }

  if (isCrew) {
    bg = '#6366f1';
    glyph = '⚡';
  }

  return L.divIcon({
    className: 'civicfix-custom-marker',
    html: `
      <div style="position: relative; width: 32px; height: 38px; display: flex; flex-direction: column; align-items: center;">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="32" height="32" style="filter: drop-shadow(0 4px 6px rgba(0,0,0,0.5));">
          <path fill="${bg}" stroke="#ffffff" stroke-width="1.6" d="M12 0C7.58 0 4 3.58 4 8c0 5.25 7 13 8 16 1-3 8-10.75 8-16 0-4.42-3.58-8-8-8z"/>
          <circle cx="12" cy="8" r="4.2" fill="#0f172a"/>
        </svg>
        <span style="position: absolute; top: 2px; left: 0; right: 0; text-align: center; color: #ffffff; font-size: 8px; font-weight: 800; font-family: monospace;">
          ${glyph}
        </span>
      </div>
    `,
    iconSize: [32, 38],
    iconAnchor: [16, 36],
    popupAnchor: [0, -34],
  });
}

/**
 * Picker pin marker icon for citizen issue reporting
 */
const pickerPinIcon = L.divIcon({
  className: 'civicfix-picker-marker',
  html: `
    <div style="position: relative; width: 34px; height: 42px; display: flex; flex-direction: column; align-items: center;">
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="34" height="34" style="filter: drop-shadow(0 4px 8px rgba(0,0,0,0.6));">
        <path fill="#2563eb" stroke="#ffffff" stroke-width="1.8" d="M12 0C7.58 0 4 3.58 4 8c0 5.25 7 13 8 16 1-3 8-10.75 8-16 0-4.42-3.58-8-8-8z"/>
        <circle cx="12" cy="8" r="4.5" fill="#ffffff"/>
        <circle cx="12" cy="8" r="2.5" fill="#1e3a8a"/>
      </svg>
    </div>
  `,
  iconSize: [34, 42],
  iconAnchor: [17, 40],
  popupAnchor: [0, -38],
});

export const CivicFixMap: React.FC<CivicFixMapProps> = ({
  mode = 'viewer',
  center,
  zoom,
  height = '420px',
  latitude = 17.4399,
  longitude = 78.4983,
  onLocationChange,
  disabled = false,
  complaints = [],
  onSelectComplaint,
  workOrders = [],
  onSelectWorkOrder,
  providerOverride,
}) => {
  const navigate = useNavigate();

  // Active keyless CARTO Dark Matter raster tile configuration
  const tileConfig = useMemo(() => resolveTileConfig(), []);
  const mapConfig = useMemo(() => getMapConfig(providerOverride), [providerOverride]);

  const initialCenter: [number, number] = useMemo(() => {
    if (center && validateCoordinates(center[0], center[1])) return center;
    if (validateCoordinates(latitude, longitude)) return [latitude, longitude];
    return mapConfig.defaultCenter;
  }, [center, latitude, longitude, mapConfig.defaultCenter]);

  const initialZoom: number = zoom || (mode === 'picker' ? 15 : mapConfig.defaultZoom);

  const [tileErrors, setTileErrors] = useState<number>(0);
  const [retryCount, setRetryCount] = useState<number>(0);
  const [isLocating, setIsLocating] = useState<boolean>(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  // Manual GPS entry states
  const [manualLat, setManualLat] = useState<string>(String(latitude));
  const [manualLon, setManualLon] = useState<string>(String(longitude));
  const [manualError, setManualError] = useState<string | null>(null);

  // Sync manual inputs when external coords change in picker mode
  useEffect(() => {
    setManualLat(String(latitude));
    setManualLon(String(longitude));
  }, [latitude, longitude]);

  // Handle browser device GPS geolocation
  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setGeoError('Geolocation is not supported by your browser.');
      return;
    }

    setIsLocating(true);
    setGeoError(null);

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const cleanLat = Number(pos.coords.latitude.toFixed(5));
        const cleanLon = Number(pos.coords.longitude.toFixed(5));
        setIsLocating(false);
        if (onLocationChange) onLocationChange(cleanLat, cleanLon);
      },
      (err) => {
        setIsLocating(false);
        setGeoError(err.message || 'Unable to retrieve your current location.');
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
    );
  };

  // Handle manual coordinate input application
  const handleApplyManualCoords = (e: React.FormEvent) => {
    e.preventDefault();
    setManualError(null);

    const latNum = parseFloat(manualLat.trim());
    const lonNum = parseFloat(manualLon.trim());

    if (isNaN(latNum) || isNaN(lonNum)) {
      setManualError('Please enter valid numeric latitude and longitude values.');
      return;
    }

    if (!validateCoordinates(latNum, lonNum)) {
      setManualError('Latitude must be between -90 and 90; Longitude between -180 and 180.');
      return;
    }

    const cleanLat = Number(latNum.toFixed(5));
    const cleanLon = Number(lonNum.toFixed(5));

    if (onLocationChange) {
      onLocationChange(cleanLat, cleanLon);
    }
  };

  // Collect points for auto-fit in viewer or crew modes
  const viewerPoints = useMemo<[number, number][]>(() => {
    if (mode === 'viewer') {
      return complaints
        .filter((c) => validateCoordinates(c.latitude, c.longitude))
        .map((c) => [c.latitude, c.longitude]);
    }
    if (mode === 'crew') {
      return workOrders
        .filter((w) => w.complaint_latitude && w.complaint_longitude && validateCoordinates(w.complaint_latitude, w.complaint_longitude))
        .map((w) => [w.complaint_latitude!, w.complaint_longitude!]);
    }
    return [];
  }, [mode, complaints, workOrders]);

  return (
    <MapErrorBoundary fallbackHeight={height}>
      <div className="flex flex-col space-y-2 w-full">
        {/* Tile warning banner with Retry option if tile provider encounters issues */}
        {tileErrors >= 6 && (
          <div className="flex items-center justify-between p-2.5 bg-slate-900 border border-amber-500/50 rounded-xl text-amber-300 text-xs shadow-sm">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0" />
              <span>Map tiles are loading slowly or offline. Stored incident coordinates remain active.</span>
            </div>
            <button
              type="button"
              onClick={() => {
                setTileErrors(0);
                setRetryCount((k) => k + 1);
              }}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-lg text-[11px] font-bold transition"
            >
              <RefreshCw className="w-3 h-3" />
              Retry Tiles
            </button>
          </div>
        )}

        {/* Map Container */}
        <div
          className="relative rounded-2xl overflow-hidden border border-slate-700/60 shadow-lg"
          style={{ height, minHeight: height, width: '100%' }}
        >
          <MapContainer
            center={initialCenter}
            zoom={initialZoom}
            style={{ width: '100%', height: '100%', minHeight: height, background: '#0b1120' }}
            scrollWheelZoom={true}
            attributionControl={true}
          >
            <InvalidateMapSize />

            {/* Verified Public Key-Free Raster Basemap */}
            <TileLayer
              key={`esri-tile-layer-${retryCount}-${tileConfig.tileUrl}`}
              url={tileConfig.tileUrl}
              subdomains={tileConfig.subdomains}
              attribution={tileConfig.attribution}
              maxZoom={19}
              eventHandlers={{
                tileerror: () => {
                  setTileErrors((count) => Math.min(count + 1, 10));
                },
                tileload: () => {
                  if (tileErrors > 0) setTileErrors(0);
                },
              }}
            />

            {/* MODE: PICKER (Citizen Issue Pinpointing) */}
            {mode === 'picker' && (
              <>
                <LocationPickerHandler onLocationChange={onLocationChange} disabled={disabled} />
                <MapCenterUpdater target={[latitude, longitude]} zoom={initialZoom} />

                {validateCoordinates(latitude, longitude) && (
                  <Marker
                    position={[latitude, longitude]}
                    icon={pickerPinIcon}
                    draggable={!disabled}
                    eventHandlers={{
                      dragend(e) {
                        if (disabled || !onLocationChange) return;
                        const marker = e.target;
                        const pos = marker.getLatLng();
                        const cleanLat = Number(pos.lat.toFixed(5));
                        const cleanLon = Number(pos.lng.toFixed(5));
                        onLocationChange(cleanLat, cleanLon);
                      },
                    }}
                  >
                    <Popup className="civicfix-dark-popup">
                      <div className="p-2 text-xs text-slate-100 font-sans">
                        <strong className="text-brand-400 block mb-0.5">Selected Incident Location</strong>
                        <span className="font-mono text-[11px] text-slate-300">
                          {formatCoordinates(latitude, longitude)}
                        </span>
                        <p className="text-[10px] text-slate-400 mt-1">
                          Click anywhere or drag this pin to adjust defect coordinates.
                        </p>
                      </div>
                    </Popup>
                  </Marker>
                )}
              </>
            )}

            {/* MODE: VIEWER (Staff Live Issue Map & Citizen Dashboard) */}
            {mode === 'viewer' && (
              <>
                <FitBoundsUpdater points={viewerPoints} />
                {complaints.map((c) => {
                  if (!validateCoordinates(c.latitude, c.longitude)) return null;
                  const markerIcon = createCivicMarkerIcon(c.priority, c.status, false);

                  return (
                    <Marker key={c.id} position={[c.latitude, c.longitude]} icon={markerIcon}>
                      <Popup className="civicfix-dark-popup">
                        <div className="p-3 text-xs text-slate-100 font-sans min-w-[210px] max-w-[260px]">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-mono font-bold text-brand-400 text-[11px]">
                              #{c.reference_number}
                            </span>
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
                              {c.priority}
                            </span>
                          </div>

                          <h4 className="font-bold text-sm text-white line-clamp-1 mb-1">{c.title}</h4>
                          <p className="text-[11px] text-slate-400 mb-2">
                            {c.category} • <strong className="text-slate-300">{c.status.replace(/_/g, ' ')}</strong>
                          </p>

                          {c.first_image && (
                            <div className="mb-2 rounded-lg overflow-hidden border border-slate-700">
                              <img src={c.first_image} alt="Defect" className="w-full h-24 object-cover" />
                            </div>
                          )}

                          <button
                            type="button"
                            onClick={() => {
                              if (onSelectComplaint) {
                                onSelectComplaint(c.id);
                              } else {
                                navigate(`/admin/complaints/${c.id}`);
                              }
                            }}
                            className="w-full py-1.5 bg-brand-600 hover:bg-brand-700 text-white font-semibold text-xs rounded-lg transition"
                          >
                            Inspect Complaint
                          </button>
                        </div>
                      </Popup>
                    </Marker>
                  );
                })}
              </>
            )}

            {/* MODE: CREW (Field Operations Work Orders) */}
            {mode === 'crew' && (
              <>
                <FitBoundsUpdater points={viewerPoints} />
                {workOrders.map((wo) => {
                  const lat = wo.complaint_latitude;
                  const lon = wo.complaint_longitude;
                  if (!lat || !lon || !validateCoordinates(lat, lon)) return null;

                  const markerIcon = createCivicMarkerIcon('P1', wo.status, true);
                  const googleNavUrl = `https://www.google.com/maps/dir/?api=1&destination=${lat},${lon}`;

                  return (
                    <Marker key={wo.id} position={[lat, lon]} icon={markerIcon}>
                      <Popup className="civicfix-dark-popup">
                        <div className="p-3 text-xs text-slate-100 font-sans min-w-[220px] max-w-[270px]">
                          <div className="flex items-center justify-between mb-1.5">
                            <span className="font-mono font-bold text-indigo-400 text-[11px]">
                              #{wo.complaint_reference || wo.id.slice(0, 8)}
                            </span>
                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                              {wo.status}
                            </span>
                          </div>

                          <h4 className="font-bold text-sm text-white line-clamp-1 mb-1">{wo.title}</h4>
                          <p className="text-[11px] text-slate-400 mb-2 line-clamp-2">
                            {wo.instructions || 'Proceed to site coordinates.'}
                          </p>

                          <div className="flex gap-2 pt-1">
                            <a
                              href={googleNavUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex-1 text-center py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-[11px] rounded-lg transition inline-flex items-center justify-center gap-1"
                            >
                              <Compass className="w-3 h-3" />
                              Navigate GPS
                            </a>

                            <button
                              type="button"
                              onClick={() => {
                                if (onSelectWorkOrder) onSelectWorkOrder(wo.id);
                              }}
                              className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-semibold text-[11px] rounded-lg transition"
                            >
                              Select
                            </button>
                          </div>
                        </div>
                      </Popup>
                    </Marker>
                  );
                })}
              </>
            )}
          </MapContainer>
        </div>

        {/* PICKER MODE: Location Tools & Manual Coordinate Fallback */}
        {mode === 'picker' && (
          <div className="space-y-2 pt-1">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onClick={handleUseCurrentLocation}
                disabled={disabled || isLocating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-semibold transition disabled:opacity-50"
              >
                {isLocating ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-brand-600" />
                ) : (
                  <Navigation className="w-3.5 h-3.5 text-brand-600" />
                )}
                <span>{isLocating ? 'Acquiring GPS...' : 'Use My Current Location'}</span>
              </button>

              <div className="text-[11px] font-mono text-slate-600 bg-slate-100 px-2.5 py-1 rounded-lg">
                📍 {formatCoordinates(latitude, longitude)}
              </div>
            </div>

            {geoError && (
              <p className="text-[11px] text-rose-600 bg-rose-50 border border-rose-200 p-2 rounded-xl">
                {geoError}
              </p>
            )}

            {/* Manual Coordinate Entry Inputs */}
            <form onSubmit={handleApplyManualCoords} className="p-3 bg-slate-50 border border-slate-200 rounded-2xl space-y-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                Manual GPS Coordinate Entry (Fallback)
              </span>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-slate-500 font-semibold block mb-0.5">Latitude</label>
                  <input
                    type="text"
                    value={manualLat}
                    onChange={(e) => setManualLat(e.target.value)}
                    placeholder="17.4399"
                    className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-300 rounded-lg font-mono focus:ring-1 focus:ring-brand-500"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 font-semibold block mb-0.5">Longitude</label>
                  <input
                    type="text"
                    value={manualLon}
                    onChange={(e) => setManualLon(e.target.value)}
                    placeholder="78.4983"
                    className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-300 rounded-lg font-mono focus:ring-1 focus:ring-brand-500"
                  />
                </div>
              </div>

              {manualError && (
                <p className="text-[11px] text-rose-600 font-medium">{manualError}</p>
              )}

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={disabled}
                  className="px-3 py-1 bg-brand-600 hover:bg-brand-700 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50"
                >
                  Update Pin on Map
                </button>
              </div>
            </form>
          </div>
        )}
      </div>
    </MapErrorBoundary>
  );
};
